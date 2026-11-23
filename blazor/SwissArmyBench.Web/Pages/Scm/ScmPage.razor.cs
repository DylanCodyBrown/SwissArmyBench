using Microsoft.AspNetCore.Components;
using Microsoft.AspNetCore.Components.Web;
using Microsoft.JSInterop;

using SwissArmyBench.Web.Api;
using SwissArmyBench.Web.Api.Git;
using SwissArmyBench.Web.State;

namespace SwissArmyBench.Web.Pages.Scm;

public partial class ScmPage
{
    // The side bar's width: VS Code's sash keeps it between these.
    private const double NarrowestSidebar = 170;
    private const double WidestSidebar = 800;
    private const double DefaultSidebar = 300;

    private readonly Dictionary<string, ScmHistory> _histories = [];
    private readonly Dictionary<string, IReadOnlyList<ScmResource>> _opened = [];
    private readonly Dictionary<string, string> _messages = [];
    private readonly HashSet<string> _collapsedGroups = [];
    private readonly HashSet<string> _collapsedPanes = [];
    private string _title = "Git";
    private ScmChanges? _changes;
    private ScmStatus? _status;
    private string? _currentWhich;
    private bool _tree;
    private ShownDiff? _shown;
    private ScmDiff? _diff;
    private OpenScmMenu? _menu;
    private QuickPickRequest? _pick;
    private DialogRequest? _dialog;
    private HoverCard? _hover;
    private double _sidebarWidth = DefaultSidebar;
    private (double X, double Width)? _sashFrom;
    private ElementReference _sash;
    private IJSObjectReference? _editorModule;

    [Inject]
    private GitClient Git { get; set; } = default!;

    [Inject]
    private LiveUpdates Live { get; set; } = default!;

    [Inject]
    private ThemeState Theme { get; set; } = default!;

    [Inject]
    private RailState Rail { get; set; } = default!;

    [Inject]
    private Notes Notes { get; set; } = default!;

    [Inject]
    private IJSRuntime Js { get; set; } = default!;

    [Inject]
    private SwissArmyBench.Web.Api.Files.FileChooser Files { get; set; } = default!;

    /// <summary>The repository the graph and the title actions are for.</summary>
    public ScmRepository? Current => (_changes?.Repositories ?? []).FirstOrDefault(r => r.Which == _currentWhich) ?? _changes?.Repositories.FirstOrDefault();

    private int? Total => _changes?.Repositories.Sum(r => r.Count) is > 0 and var total ? total : null;

    private string SidebarWidth => FormattableString.Invariant($"width: {_sidebarWidth}px;");

    protected override async Task OnInitializedAsync()
    {
        Live.NoticeArrived += OnNotice;
        Theme.Changed += OnThemeChanged;
        _title = Rail.ExtensionAreas.FirstOrDefault(a => a.Area == "scm")?.Name ?? _title;
        _tree = await Js.InvokeAsync<string?>("sab.recall", "scm.viewMode") == "tree";
        await Js.InvokeVoidAsync("sab.setTitle", _title);
        await LoadAsync();
    }

    protected override async Task OnAfterRenderAsync(bool firstRender)
    {
        if (firstRender)
        {
            // Monaco's stylesheet holds the codicon font the page draws with.
            _editorModule = await Js.InvokeAsync<IJSObjectReference>("import", "./js/codeEditor.js");
        }
    }

    /// <summary>The changes and GitHub sync's state, then the graph of the repository in front.</summary>
    public async Task LoadAsync()
    {
        var changes = CallAsync(Git.ChangesAsync);
        var status = CallAsync(() => Git.StatusAsync(remote: true));
        _changes = await changes;
        _status = await status;
        StateHasChanged();
        if (Current is { } repo && _changes?.SignedIn == true)
        {
            await LoadHistoryAsync(repo);
        }
    }

    /// <summary>A page of the repository's history (more: the next page added).</summary>
    public async Task LoadHistoryAsync(ScmRepository repo, bool more = false)
    {
        var had = _histories.GetValueOrDefault(repo.Which);
        var page = more && had is not null ? had.Page + 1 : 1;
        if (await CallAsync(() => Git.HistoryAsync(repo.Which, page)) is not { } got)
        {
            return;
        }
        _histories[repo.Which] = more && had is not null ? got with { Rows = [.. had.Rows, .. got.Rows] } : got;
        StateHasChanged();
    }

    public void SelectRepository(ScmRepository repo)
    {
        _currentWhich = repo.Which;
        _ = LoadHistoryAsync(repo);
    }

    /// <summary>A call whose refusal shows as the error toast (VS Code's notification).</summary>
    public async Task<T?> CallAsync<T>(Func<Task<T>> call)
        where T : class
    {
        try
        {
            return await call();
        }
        catch (ApiException error)
        {
            Notes.Error(error);
            return null;
        }
    }

    public async Task<bool> CallAsync(Func<Task> call)
    {
        try
        {
            await call();
            return true;
        }
        catch (ApiException error)
        {
            Notes.Error(error);
            return false;
        }
    }

    private async Task ToggleViewAsync()
    {
        _tree = !_tree;
        await Js.InvokeVoidAsync("sab.remember", "scm.viewMode", _tree ? "tree" : "list");
    }

    private void TogglePane(string id)
    {
        if (!_collapsedPanes.Remove(id))
        {
            _collapsedPanes.Add(id);
        }
    }

    public void ToggleGroup(string key)
    {
        if (!_collapsedGroups.Remove(key))
        {
            _collapsedGroups.Add(key);
        }
    }

    public void Menu(double x, double y, string label, IReadOnlyList<ScmMenuItem?> items) => _menu = new OpenScmMenu(x, y, label, items);

    public void ShowHover(HoverCard? hover) => _hover = hover;

    /// <summary>A quick pick: the value picked, or null.</summary>
    public Task<string?> PickAsync(string placeholder, IReadOnlyList<PickChoice> items, bool free = false)
    {
        var request = new QuickPickRequest(placeholder, items, free, new TaskCompletionSource<string?>(TaskCreationOptions.RunContinuationsAsynchronously));
        _pick = request;
        StateHasChanged();
        return request.Answer.Task;
    }

    /// <summary>VS Code's modal dialog: the button picked, or null.</summary>
    public Task<string?> AskAsync(string message, string detail, params string[] buttons)
    {
        var request = new DialogRequest(message, detail, buttons, new TaskCompletionSource<string?>(TaskCreationOptions.RunContinuationsAsynchronously));
        _dialog = request;
        StateHasChanged();
        return request.Answer.Task;
    }

    private async Task SashDownAsync(PointerEventArgs e)
    {
        _sashFrom = (e.ClientX, _sidebarWidth);
        var module = await Js.InvokeAsync<IJSObjectReference>("import", "./js/canvas.js");
        await module.InvokeVoidAsync("capture", _sash, e.PointerId);
    }

    private void SashMove(PointerEventArgs e)
    {
        if (_sashFrom is { } from)
        {
            _sidebarWidth = Math.Clamp(from.Width + e.ClientX - from.X, NarrowestSidebar, WidestSidebar);
        }
    }

    private void OnNotice(Notice notice)
    {
        if (notice.Type is "sync_changed" or "project_changed" or "projects_changed")
        {
            _ = InvokeAsync(LoadAsync);
        }
    }

    private void OnThemeChanged() => _ = InvokeAsync(StateHasChanged);

    public async ValueTask DisposeAsync()
    {
        Live.NoticeArrived -= OnNotice;
        Theme.Changed -= OnThemeChanged;
        if (_editorModule is not null)
        {
            try
            {
                await _editorModule.DisposeAsync();
            }
            catch (JSDisconnectedException)
            {
                // the page is closing
            }
        }
    }
}
