using Microsoft.AspNetCore.Components;
using Microsoft.AspNetCore.Components.Web;
using Microsoft.JSInterop;

using SwissArmyBench.Web.Api;
using SwissArmyBench.Web.Api.Connections;
using SwissArmyBench.Web.Api.Files;
using SwissArmyBench.Web.Api.Projects;
using SwissArmyBench.Web.Api.Workbench;
using SwissArmyBench.Web.Components;
using SwissArmyBench.Web.Pages.Workbench.Tabs;
using SwissArmyBench.Web.State;

namespace SwissArmyBench.Web.Pages.Workbench;

public partial class WorkbenchPage
{
    private const string NothingSaves = "Nothing that saves is in front";


    private readonly TabLayout _layout = new();
    private readonly List<OpenDocument> _documents = [];
    private readonly Dictionary<int, OpenDocument> _byKey = [];
    private readonly Dictionary<int, int> _problems = [];
    private int _nextKey;
    private bool _loading;
    private CodeTree? _tree;
    private IReadOnlyList<RecentFile> _recent = [];
    private IReadOnlyList<string> _connections = [];
    private bool _showFiles = true;
    private bool _showBlades;
    private bool _full;
    private ShownMenu? _menu;
    private (string Words, string Address)? _wrongPage;
    private Exception? _error;
    private string? _shownFor;
    private IJSObjectReference? _module;
    private IJSObjectReference? _keys;
    private DotNetObjectReference<WorkbenchPage>? _self;

    [Inject]
    private WorkbenchClient Workbench { get; set; } = default!;

    [Inject]
    private ExportsClient Exports { get; set; } = default!;

    [Inject]
    private ScriptIdeClient ScriptIde { get; set; } = default!;

    [Inject]
    private ProjectsClient ProjectsApi { get; set; } = default!;

    [Inject]
    private ConnectionsClient ConnectionsApi { get; set; } = default!;

    [Inject]
    private SwissArmyBench.Web.Api.Environment.EnvironmentClient EnvironmentApi { get; set; } = default!;

    [Inject]
    private FileChooser Files { get; set; } = default!;

    [Inject]
    private PythonSession Session { get; set; } = default!;

    [Inject]
    private ProjectState Project { get; set; } = default!;

    [Inject]
    private Dialogs Dialogs { get; set; } = default!;

    [Inject]
    private NavigationManager Nav { get; set; } = default!;

    [Inject]
    private Notes Notes { get; set; } = default!;

    [Inject]
    private IJSRuntime Js { get; set; } = default!;

    [Inject]
    private Commands Palette { get; set; } = default!;

    [Inject]
    private CollaborationState Collaboration { get; set; } = default!;

    [Inject]
    private PageObjects Shown { get; set; } = default!;

    /// <summary>notebooks or scripts: the two pages share this component.</summary>
    [Parameter, EditorRequired]
    public string Page { get; set; } = "notebooks";

    [Parameter]
    public string? Path { get; set; }

    [Parameter]
    public bool New { get; set; }

    /// <summary>What ?new= asks for: a file type's id ("sql": the Tables page's "+"), else the page's own kind. The
    /// New file dialog opens for it: its name first.</summary>
    [Parameter]
    public string? NewKind { get; set; }

    /// <summary>With ?new=: the file the new one is made from (?from=), filled into the dialog.</summary>
    [Parameter]
    public string? NewFrom { get; set; }

    /// <summary>The script's line to reveal (its cursor there), or the notebook's cell to select (the classic file.openCell).</summary>
    [Parameter]
    public int? Line { get; set; }

    [Parameter]
    public int? Cell { get; set; }

    private bool IsNotebooks => Page == "notebooks";

    private string Kind => IsNotebooks ? "notebook" : "script";

    private string KindWord => IsNotebooks ? "notebook" : "script";

    /// <summary>The document in front of the focused group.</summary>
    private OpenDocument? Front => _layout.Current is { } key && _byKey.TryGetValue(key, out var doc) ? doc : null;

    private string Title => Front?.Title ?? (IsNotebooks ? "Notebooks" : "Scripts");

    protected override async Task OnInitializedAsync()
    {
        Session.Changed += Redraw;
        Project.Changed += Redraw;
        Palette.SetPageCommands(PageCommands);
        Palette.SetPageAnswers(AgentAnswerAsync);
        _showFiles = await Js.InvokeAsync<string?>("sab.recall", $"{Page}.files") != "0";
        _showBlades = await Js.InvokeAsync<string?>("sab.recall", $"{Page}.blades") == "1";
        _showExplorer = await Js.InvokeAsync<string?>("sab.recall", $"{Page}.explorer") == "1";
        await RecallEnvironmentAsync();
        Live.NoticeArrived += OnInlineNotice;
        Live.NoticeArrived += OnFileNotice;
        Live.NoticeArrived += OnPythonNotice;
        await Task.WhenAll(LoadTreeAsync(), LoadConnectionsAsync(), LoadSqlConnectionsAsync(), LoadNewFileOptionsAsync(), LoadBetaAsync(), LoadInlineAsync(), LoadPythonsAsync(), LoadVaultsAsync());
    }

    private async Task LoadBetaAsync()
    {
        try
        {
            _betaOn = (await SettingsApi.BetaAsync()).On;
        }
        catch (ApiException)
        {
            _betaOn = false; // the menu offers to turn it on
        }
    }

    protected override async Task OnAfterRenderAsync(bool firstRender)
    {
        if (firstRender)
        {
            _self = DotNetObjectReference.Create(this);
            _module = await Js.InvokeAsync<IJSObjectReference>("import", "./js/workbench.js");
            _keys = await _module.InvokeAsync<IJSObjectReference>("keys", _self);
            await ReadWindowAsync();
        }
        await RevealPendingAsync();
        ShowFront();
        await AskOnceDrawnAsync();
    }

    /// <summary>What an address asks for, as one key: the one the page last acted on is not acted on again.</summary>
    private static string AddressKey(string? path, string fresh, string? blade, int? line, int? cell, string? codeFile) =>
        $"{path}|{fresh}|{blade}|{line}|{cell}|{codeFile}";

    protected override async Task OnParametersSetAsync()
    {
        var wanted = AddressKey(Path, New ? NewKind ?? "1" : string.Empty, Blade, Line, Cell, CodeFile);
        if (wanted == _shownFor)
        {
            return;
        }
        _shownFor = wanted;
        _wrongPage = null;
        if (Blade is { Length: > 0 } blade && !IsNotebooks)
        {
            await OpenBladeAsync(blade);
        }
        else if (CodeFile is { Length: > 0 } file && !IsNotebooks)
        {
            await OpenCodeFileAsync(file);
        }
        else if (Path is { Length: > 0 } path)
        {
            await OpenPathAsync(path);
            RevealAfterOpen(path);
        }
        else
        {
            AskOnceDrawn(); // ?new=<type>: the New file dialog for it, once the page is drawn
            _recent = await RecentAsync();
        }
        await Js.InvokeVoidAsync("sab.setTitle", Title);
    }

    /// <summary>A key the page acts on (workbench.js): told by name.</summary>
    [JSInvokable]
    public Task PageKey(string name) => InvokeAsync(async () =>
    {
        await PageKeyAsync(name);
        StateHasChanged();
    });

    private Task PageKeyAsync(string name) => name switch
    {
        _ when name.StartsWith("cell:", StringComparison.Ordinal) => Front?.NotebookView?.CommandAsync(name[5..]) ?? Task.CompletedTask,
        "palette" => ShowPalette(),
        "save" => SaveFrontAsync(),
        "saveAs" => SaveAsAsync(Front),
        "open" => OpenAsync(),
        "run" => Front is { } doc ? RunMainAsync(doc) : Task.CompletedTask,
        "splitRight" => SplitAsync(Front, SplitSide.Right),
        "nextDoc" => ShowNextAsync(1),
        "previousDoc" => ShowNextAsync(-1),
        "fullScreen" => FullScreenAsync(),
        "files" => ToggleFilesAsync(),
        "debug" when Front is { IsNotebook: false } doc => DebugAsync(doc),
        "searchScripts" when !IsNotebooks => Toggle(() => _searching = true),
        "escape" when _helpCard is not null => Toggle(() => _helpCard = null),
        "escape" when _lineage is not null => Toggle(() => _lineage = null),
        "escape" when _full => FullScreenAsync(),
        "help" => HelpAtCursorAsync(),
        "nextPane" => CyclePaneAsync(1),
        "previousPane" => CyclePaneAsync(-1),
        "source" => FocusSourceAsync(),
        "explorer" => ToggleExplorerAsync(),
        _ => Task.CompletedTask,
    };

    private static Task Toggle(Action change)
    {
        change();
        return Task.CompletedTask;
    }

    private async Task<IReadOnlyList<RecentFile>> RecentAsync()
    {
        try
        {
            return (await Workbench.HomeAsync()).Recent;
        }
        catch (ApiException)
        {
            return [];
        }
    }

    private async Task LoadTreeAsync()
    {
        try
        {
            _tree = await Workbench.TreeAsync(Page);
        }
        catch (ApiException)
        {
            _tree = new CodeTree(null, null, []); // the pane says no project is open
        }
    }

    private async Task LoadConnectionsAsync()
    {
        try
        {
            _connections = (await ConnectionsApi.CardsAsync())
                .Select(c => c.Name)
                .OrderBy(n => n, StringComparer.OrdinalIgnoreCase)
                .ToList();
        }
        catch (ApiException)
        {
            _connections = []; // a SQL cell still runs on DuckDB's open tables
        }
    }

    /// <summary>A menu under the control clicked (or at the pointer for a right click).</summary>
    private Task ShowMenuAsync(MouseEventArgs at, (string Title, IReadOnlyList<MenuEntry> Entries) menu)
    {
        _lastClick = at;
        _menu = new ShownMenu(menu.Title, menu.Entries, at.ClientX, at.ClientY + 4);
        return Task.CompletedTask;
    }

    /// <summary>The page's commands for the one palette (State/Commands, Layout/CommandPalette): each runs under the
    /// page's error note and the page draws its outcome, the palette that asked having gone.</summary>
    private IReadOnlyList<PaletteCommand> PageCommands() =>
        [.. Commands().Select(c => c with { Run = () => InvokeAsync(async () =>
        {
            await GuardAsync(c.Run);
            StateHasChanged();
        }) })];

    private Task ShowPalette()
    {
        Palette.Show("palette");
        return Task.CompletedTask;
    }

    /// <summary>An action whose refusal shows in the page's error note.</summary>
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
        catch (InvalidOperationException error)
        {
            _error = error; // a move that cannot be made now, in its own words
        }
    }

    private Task InterruptAsync() => GuardAsync(Session.InterruptAsync);

    private async Task RestartAsync()
    {
        // The project's one session: every notebook's and script's variables go, so it is asked first.
        if (Session.Shared is not null && !await Dialogs.AskYesNoAsync("Restart", "Restart the project's Python session? Every variable is cleared, for every notebook and script of the project.", "Restart"))
        {
            return;
        }
        await GuardAsync(Session.RestartAsync);
        if (Session.Shared is not null)
        {
            await Notes.SayAsync("The project's Python session was restarted: every variable is cleared.");
        }
    }

    private async Task ToggleFilesAsync()
    {
        _showFiles = !_showFiles;
        await Js.InvokeVoidAsync("sab.remember", $"{Page}.files", _showFiles ? "1" : "0");
    }

    private async Task ToggleBladesAsync()
    {
        _showBlades = !_showBlades;
        await Js.InvokeVoidAsync("sab.remember", $"{Page}.blades", _showBlades ? "1" : "0");
    }

    private async Task FullScreenAsync()
    {
        _full = !_full;
        if (_module is not null)
        {
            await _module.InvokeVoidAsync("fullScreen", _full);
        }
    }

    private void Problems(OpenDocument doc, int count) => _problems[doc.Key] = count;

    private string ProblemWords(OpenDocument doc) => _problems.GetValueOrDefault(doc.Key) switch
    {
        0 => string.Empty,
        1 => "1 problem",
        var n => $"{n} problems",
    };

    private void Redraw() => _ = InvokeAsync(StateHasChanged);

    public async ValueTask DisposeAsync()
    {
        Palette.WithdrawPageCommands(PageCommands);
        Palette.WithdrawPageAnswers(AgentAnswerAsync);
        ClearShown();
        Session.Changed -= Redraw;
        Project.Changed -= Redraw;
        Live.NoticeArrived -= OnInlineNotice;
        Live.NoticeArrived -= OnFileNotice;
        Live.NoticeArrived -= OnPythonNotice;
        try
        {
            if (_keys is not null)
            {
                await _keys.InvokeVoidAsync("stop");
                await _keys.DisposeAsync();
            }
            if (_module is not null)
            {
                await _module.InvokeVoidAsync("fullScreen", false);
                await _module.DisposeAsync();
            }
        }
        catch (JSDisconnectedException)
        {
            // the page is going
        }
        _self?.Dispose();
    }
}
