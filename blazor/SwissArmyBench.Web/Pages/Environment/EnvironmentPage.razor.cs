using Microsoft.AspNetCore.Components;
using Microsoft.JSInterop;

using SwissArmyBench.Web.Api;
using SwissArmyBench.Web.Api.Environment;
using SwissArmyBench.Web.State;

namespace SwissArmyBench.Web.Pages.Environment;

public partial class EnvironmentPage : IDisposable
{
    private const string Table = "table";
    private const string Structure = "structure";
    private const string Setting = "setting";
    private const string Library = "library";
    private const int TypingPauseMilliseconds = 200;

    /// <summary>The address's word for each tab (?at=), as the classic page names them.</summary>
    private static readonly Dictionary<string, string> _tabWords = new()
    {
        ["tables"] = Table,
        ["variables"] = "variable",
        ["structures"] = Structure,
        ["settings"] = Setting,
        ["libraries"] = Library,
    };

    private EnvironmentAnswer? _answer;
    private Exception? _error;
    private string _search = string.Empty;
    private CancellationTokenSource? _typing;

    [Inject]
    private EnvironmentClient Environment { get; set; } = default!;

    [Inject]
    private LiveUpdates Live { get; set; } = default!;

    [Inject]
    private Dialogs Dialogs { get; set; } = default!;

    [Inject]
    private NavigationManager Nav { get; set; } = default!;

    [Inject]
    private IJSRuntime Js { get; set; } = default!;

    [SupplyParameterFromQuery(Name = "at")]
    public string? At { get; set; }

    /// <summary>The tab shown: the address's, else Tables.</summary>
    private string Tab => At is not null && _tabWords.TryGetValue(At, out var kind) ? kind : Table;

    protected override async Task OnInitializedAsync()
    {
        await Js.InvokeVoidAsync("sab.setTitle", "Environment");
        Live.NoticeArrived += OnNotice;
        await LoadAsync();
    }

    private static string TabParameterOf(string kind) => _tabWords.First(w => w.Value == kind).Key;

    private async Task LoadAsync()
    {
        try
        {
            _answer = await Environment.ListingAsync(_search);
            _error = null;
        }
        catch (ApiException error)
        {
            _error = error;
        }
    }

    private async Task SearchAsync(ChangeEventArgs e)
    {
        _search = e.Value?.ToString() ?? string.Empty;
        _typing?.Cancel();
        _typing = new CancellationTokenSource();
        try
        {
            await Task.Delay(TypingPauseMilliseconds, _typing.Token);
        }
        catch (TaskCanceledException)
        {
            return; // more typing came: only the last pause looks
        }
        await LoadAsync();
    }

    /// <summary>A table opens as its grid on the Grids page; a structure on the classic Structures page for now.</summary>
    private async Task OpenAsync(EnvironmentItem item)
    {
        if (item.Kind == Structure)
        {
            Nav.NavigateTo($"/workspace?open=structures&name={Uri.EscapeDataString(item.Name)}", forceLoad: true);
            return;
        }
        await RunAsync(async () =>
        {
            var opened = await Environment.OpenAsync(item.Kind, item.Name);
            var grid = opened.Link?.Grid;
            Nav.NavigateTo(grid is null ? "grids" : $"grids?grid={Uri.EscapeDataString(grid)}");
        });
    }

    private async Task RenameAsync(EnvironmentItem item)
    {
        var to = await Dialogs.AskTextAsync($"Rename {item.Name}", "Every place that uses it follows.", "Name", item.Name, "Rename");
        if (!string.IsNullOrWhiteSpace(to) && to != item.Name)
        {
            await RunAsync(() => Environment.RenameAsync(item.Kind, item.Name, to.Trim()));
        }
    }

    private async Task RemoveAsync(EnvironmentItem item)
    {
        if (await Dialogs.AskYesNoAsync($"Remove {item.Name}?", "It leaves the project's environment.", "Remove", danger: true))
        {
            await RunAsync(() => Environment.RemoveAsync(item.Kind, item.Name));
        }
    }

    private Task PinAsync(EnvironmentItem item) => RunAsync(() => Environment.PinAsync(item.Name, item.Pinned != true));

    private Task UpdateAsync(EnvironmentItem item) => RunAsync(() => Environment.UpdateAsync(item.Name));

    private Task CheckAsync() => RunAsync(() => Environment.CheckLibrariesAsync());

    private async Task RunAsync(Func<Task> work)
    {
        try
        {
            await work();
            _error = null;
        }
        catch (ApiException error)
        {
            _error = error;
        }
        await LoadAsync();
    }

    private void OnNotice(Notice notice)
    {
        if (notice.Type == "environment_changed")
        {
            _ = InvokeAsync(async () =>
            {
                await LoadAsync();
                StateHasChanged();
            });
        }
    }

    public void Dispose()
    {
        Live.NoticeArrived -= OnNotice;
        _typing?.Dispose();
        GC.SuppressFinalize(this);
    }
}
