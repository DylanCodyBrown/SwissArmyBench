using System.Text.Json;

using Microsoft.AspNetCore.Components;
using Microsoft.JSInterop;

using SwissArmyBench.Web.Api;
using SwissArmyBench.Web.Api.Workbench;

namespace SwissArmyBench.Web.Pages.Workbench;

public partial class BladesPane
{
    private IReadOnlyList<BladeSummary> _mine = [];
    private IReadOnlyList<StarterFamily> _starters = [];
    private string _search = string.Empty;
    private bool _loaded;
    private bool _new;
    private bool _importing;
    private bool _folders;
    private ShownMenu? _menu;

    [Inject]
    private SwissArmyBench.Web.Api.Blades.BladesClient Blades { get; set; } = default!;

    [Inject]
    private IJSRuntime Js { get; set; } = default!;

    [Inject]
    private SwissArmyBench.Web.State.Notes Notes { get; set; } = default!;

    /// <summary>A blade's name clicked: its IDE as a tab.</summary>
    [Parameter]
    public EventCallback<string> OnOpen { get; set; }

    /// <summary>A blade just made (New blade): opened with its Properties.</summary>
    [Parameter]
    public EventCallback<string> OnMade { get; set; }

    /// <summary>Import from a project… (the page's import dialog).</summary>
    [Parameter]
    public EventCallback OnImportProject { get; set; }
    private Exception? _error;

    [Inject]
    private WorkbenchClient Workbench { get; set; } = default!;

    /// <summary>A blade's line to put into the code.</summary>
    [Parameter]
    public EventCallback<string> OnInsert { get; set; }

    /// <summary>Your blades first, then each starter family; only the ones whose name or words hold the search.</summary>
    private IEnumerable<BladeGroup> Groups =>
        new[] { new BladeGroup("Your blades", Matching(_mine).OrderByDescending(b => b.Pinned).ToList(), true) }
            .Concat(_starters.Select(f => new BladeGroup(f.Family, Matching(f.Blades), _search.Length > 0)))
            .Where(g => g.Blades.Count > 0);

    [Inject]
    private SwissArmyBench.Web.State.LiveUpdates Live { get; set; } = default!;

    protected override Task OnInitializedAsync()
    {
        Live.NoticeArrived += OnNotice;
        return LoadAsync();
    }

    /// <summary>A blade saved, made, renamed or removed anywhere (blades_changed): the list read again.</summary>
    private void OnNotice(SwissArmyBench.Web.State.Notice notice)
    {
        if (notice.Type == "blades_changed")
        {
            _ = InvokeAsync(async () =>
            {
                await LoadAsync();
                StateHasChanged();
            });
        }
    }

    public void Dispose() => Live.NoticeArrived -= OnNotice;

    private async Task LoadAsync()
    {
        try
        {
            _mine = (await Workbench.BladesAsync()).Blades;
            _starters = (await Workbench.StartersAsync()).Families;
            (_error, _loaded) = (null, true);
        }
        catch (ApiException error)
        {
            _error = error;
        }
    }

    private List<BladeSummary> Matching(IEnumerable<BladeSummary> blades) =>
        blades
            .Where(b => _search.Length == 0
                || b.Name.Contains(_search, StringComparison.OrdinalIgnoreCase)
                || (b.Description ?? string.Empty).Contains(_search, StringComparison.OrdinalIgnoreCase)
                || (b.Tags ?? []).Any(t => t.Equals(_search, StringComparison.OrdinalIgnoreCase)))
            .OrderBy(b => b.Name, StringComparer.OrdinalIgnoreCase)
            .ToList();

    /// <summary>A blade as one line of code (the classic bladeEditor.ts bladeLine): a connection by sab.connection, any
    /// other by sab.blade, assigned to its variable when it makes one.</summary>
    private static string LineOf(BladeSummary blade)
    {
        var call = $"sab.{(blade.Connection is null ? "blade" : "connection")}({JsonSerializer.Serialize(blade.Name)})";
        return blade.Kind is "vault" or "secret" || string.IsNullOrEmpty(blade.Variable) ? call : $"{blade.Variable} = {call}";
    }

    private void ShowMenu(Microsoft.AspNetCore.Components.Web.MouseEventArgs at) => _menu = new ShownMenu("Blades menu",
    [
        new("Import blades…", "import", () => SetAsync(() => _importing = true)),
        new("Import from a project…", "import", () => OnImportProject.InvokeAsync()),
        new("Export every blade", "export", ExportAllAsync),
        new("Blade folders…", "folder", () => SetAsync(() => _folders = true)),
    ], at.ClientX, at.ClientY + 4);

    private static Task SetAsync(Action change)
    {
        change();
        return Task.CompletedTask;
    }

    private async Task ExportAllAsync()
    {
        await Js.InvokeVoidAsync("sab.download", "/blades/export");
        await Notes.SayAsync("Exported every blade.");
    }

    private async Task PinAsync(BladeSummary blade)
    {
        await GuardAsync(() => Blades.PinAsync(blade.Name, !blade.Pinned));
        await LoadAsync();
    }

    private async Task CopyAsOwnAsync(BladeSummary blade) => await GuardAsync(async () =>
    {
        var copied = await Blades.CopyAsync(blade.Name, null, null);
        await Notes.SayAsync($"Copied as {copied.Name}.");
        await LoadAsync();
        await OnOpen.InvokeAsync(copied.Name);
    });

    private async Task CopyLineAsync(BladeSummary blade)
    {
        await Js.InvokeAsync<bool>("sab.copy", [LineOf(blade)]);
        await Notes.SayAsync($"Copied the sab.{(blade.Connection is null ? "blade" : "connection")} line.");
    }

    private async Task MadeAsync(string name)
    {
        _new = false;
        await LoadAsync();
        await OnMade.InvokeAsync(name);
    }

    private async Task ImportedAsync()
    {
        _importing = false;
        await LoadAsync();
    }

    private async Task GuardAsync(Func<Task> action)
    {
        try
        {
            await action();
            _error = null;
        }
        catch (ApiException error)
        {
            _error = error;
        }
    }
}
