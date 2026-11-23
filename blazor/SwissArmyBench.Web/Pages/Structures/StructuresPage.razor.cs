using Microsoft.AspNetCore.Components;
using Microsoft.JSInterop;

using SwissArmyBench.Web.Api;
using SwissArmyBench.Web.Api.Files;
using SwissArmyBench.Web.Api.Structures;
using SwissArmyBench.Web.State;

namespace SwissArmyBench.Web.Pages.Structures;

public partial class StructuresPage
{
    private StructureList? _list;
    private StructureDocument? _shown;
    private Exception? _error;

    [Inject]
    private StructuresClient Structures { get; set; } = default!;

    [Inject]
    private FileChooser Files { get; set; } = default!;

    [Inject]
    private Dialogs Dialogs { get; set; } = default!;

    [Inject]
    private LiveUpdates Live { get; set; } = default!;

    [Inject]
    private NavigationManager Nav { get; set; } = default!;

    [Inject]
    private IJSRuntime Js { get; set; } = default!;

    /// <summary>The structure shown (its id); none: the first open one.</summary>
    [SupplyParameterFromQuery(Name = "id")]
    public string? IdParameter { get; set; }

    protected override void OnInitialized() => Live.NoticeArrived += OnNotice;

    protected override async Task OnParametersSetAsync()
    {
        await LoadAsync();
        await Js.InvokeVoidAsync("sab.setTitle", _shown?.Name ?? "Structures");
    }

    private async Task LoadAsync()
    {
        try
        {
            _list = await Structures.ListAsync();
            var wanted = IdParameter ?? _list.Open.FirstOrDefault()?.Id;
            _shown = wanted is null || _list.Open.All(o => o.Id != wanted) ? null : await Structures.GetAsync(wanted);
            _error = null;
        }
        catch (ApiException error)
        {
            _error = error;
        }
    }

    private Task NewAsync() => ShowAsync(() => Structures.NewAsync("new_structure"));

    private async Task OpenFileAsync()
    {
        if (await Files.ChooseAsync("open", "Open a structure (JSON, YAML, XML or TOML)", null, "structure") is { } path)
        {
            await ShowAsync(() => Structures.OpenAsync(path));
        }
    }

    private async Task PasteAsync()
    {
        if (await Dialogs.AskTextAsync("Paste a structure", "JSON, YAML, XML or TOML: its format is read from the text.", "Text") is { Length: > 0 } text)
        {
            await ShowAsync(() => Structures.PasteAsync(text));
        }
    }

    private async Task ShowAsync(Func<Task<StructureDocument>> make)
    {
        try
        {
            var made = await make();
            Nav.NavigateTo($"structures?id={Uri.EscapeDataString(made.Id)}");
        }
        catch (ApiException error)
        {
            _error = error;
        }
    }

    private async Task CloseAsync(string id)
    {
        try
        {
            await Structures.CloseAsync(id);
            Nav.NavigateTo("structures");
            await LoadAsync();
        }
        catch (ApiException error)
        {
            _error = error;
        }
    }

    private async Task ChangedAsync(StructureDocument changed)
    {
        _shown = changed;
        _list = await Structures.ListAsync();
    }

    private void OnNotice(Notice notice)
    {
        if (notice.Type.StartsWith("structure", StringComparison.Ordinal))
        {
            _ = InvokeAsync(async () =>
            {
                _list = await Structures.ListAsync();
                StateHasChanged();
            });
        }
    }

    public void Dispose() => Live.NoticeArrived -= OnNotice;
}
