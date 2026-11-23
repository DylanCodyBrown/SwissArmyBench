using Microsoft.AspNetCore.Components;
using Microsoft.JSInterop;

using SwissArmyBench.Web.Api;
using SwissArmyBench.Web.Api.Widgets;
using SwissArmyBench.Web.Api.Workbench;
using SwissArmyBench.Web.Components;
using SwissArmyBench.Web.Pages.Canvas;
using SwissArmyBench.Web.State;

namespace SwissArmyBench.Web.Pages.Widgets;

public partial class WidgetsPage
{
    // The code is saved this long after typing stops; the properties are read again sooner.
    private const int SaveMs = 700;
    private const int LivePropertiesMs = 250;

    // The dock's panes and where this browser keeps their places.
    private const string LibraryPaneId = "library";
    private const string PropertiesPaneId = "properties";
    private const string DockKey = "widgets.dock";

    /// <summary>The Library on the left, Properties on the right, until the user moves them.</summary>
    private static readonly DockLayout _defaultDock = new([new(LibraryPaneId, DockSide.Left), new(PropertiesPaneId, DockSide.Right)], LeftWidth: 260);

    private readonly Dictionary<string, ElementReference> _itemRefs = [];

    private IReadOnlyList<WidgetEntry>? _widgets;
    private WidgetFull? _current;
    private WidgetContext? _context;
    private CodeEditor? _editor;
    private string _code = string.Empty;
    private string _query = string.Empty;
    private string _saved = string.Empty;
    private bool _projectOpen;
    private PaneDockState _dock = default!;
    private string? _focusName;
    private MissingPackages? _missing;
    private string? _missingPlace;
    private bool _running;
    private bool _starting;
    private string? _frame;
    private Exception? _failed;
    private int? _failedLine;
    private Exception? _listError;
    private CancellationTokenSource? _saveWait;
    private CancellationTokenSource? _propsWait;
    private string? _kernel;
    private IJSObjectReference? _keys;
    private DotNetObjectReference<WidgetsPage>? _self;

    [Inject]
    private WidgetsClient Widgets { get; set; } = default!;

    [Inject]
    private WorkbenchClient Workbench { get; set; } = default!;

    [Inject]
    private LiveUpdates Live { get; set; } = default!;

    [Inject]
    private NavigationManager Nav { get; set; } = default!;

    [Inject]
    private IJSRuntime Js { get; set; } = default!;

    [Inject]
    private PackagePrompts Prompts { get; set; } = default!;

    [SupplyParameterFromQuery(Name = "name")]
    public string? Name { get; set; }

    private string Window => ApiClient.ClientId;

    private string PlaceWords => _current?.Where == "project" ? "Copy to library" : "Copy to project";

    /// <summary>This project's, the library's, then the prebuilt ones under their packs and groups.</summary>
    private IEnumerable<(string Heading, IReadOnlyList<WidgetEntry> Items, WidgetEntry? First)> Groups
    {
        get
        {
            var shown = (_widgets ?? []).Where(w => WidgetHeadings.Matches(w, _query)).ToList();
            var project = shown.Where(w => w.Where == "project").ToList();
            var library = shown.Where(w => !w.Prebuilt && w.Where != "project").ToList();
            var prebuilt = shown.Where(w => w.Prebuilt).GroupBy(WidgetHeadings.Of).Select(g => (g.Key, (IReadOnlyList<WidgetEntry>)g.ToList()));
            return new[] { ("This project", (IReadOnlyList<WidgetEntry>)project), ("Library", library) }
                .Concat(prebuilt)
                .Where(g => g.Item2.Count > 0 || (g.Item1 == "Library" && project.Count == 0))
                .Select(g => (g.Item1, g.Item2, g.Item2.FirstOrDefault()));
        }
    }

    /// <summary>The widgets in the order the Library shows them (the arrow keys walk it).</summary>
    private IReadOnlyList<string> Flat => Groups.SelectMany(g => g.Items).Select(w => w.Name).ToList();

    /// <summary>The one line the Tab key reaches in the Library: the one with the focus, else the chosen one.</summary>
    private string? RovingName => _focusName is { } focused && Flat.Contains(focused) ? focused : _current?.Name ?? Flat.FirstOrDefault();

    protected override void OnInitialized()
    {
        _dock = new PaneDockState(Js, DockKey, _defaultDock);
        _dock.Changed += OnDockChanged;
    }

    protected override async Task OnInitializedAsync()
    {
        Live.NoticeArrived += OnNotice;
        await _dock.LoadAsync();
        await Js.InvokeVoidAsync("sab.setTitle", "Widgets");
        await Task.WhenAll(LoadListAsync(), LoadContextAsync(), LoadInlineAsync());
        var first = Name is { } wanted && (_widgets ?? []).Any(w => w.Name == wanted)
            ? wanted
            : ((_widgets ?? []).FirstOrDefault(w => !w.Prebuilt) ?? (_widgets ?? []).FirstOrDefault())?.Name;
        if (first is not null)
        {
            await SelectAsync(first, keepAddress: true);
        }
    }

    protected override async Task OnAfterRenderAsync(bool firstRender)
    {
        if (firstRender)
        {
            var module = await Js.InvokeAsync<IJSObjectReference>("import", "./js/canvas.js");
            _self = DotNetObjectReference.Create(this);
            _keys = await module.InvokeAsync<IJSObjectReference>("widgetKeys", _self);
        }
    }

    private async Task LoadListAsync()
    {
        try
        {
            var found = await Widgets.ListAsync();
            _projectOpen = !string.IsNullOrEmpty(found.ProjectFolder);
            _widgets = found.Widgets;
        }
        catch (ApiException error)
        {
            _widgets = [];
            _listError = error;
        }
    }

    private async Task LoadContextAsync()
    {
        try
        {
            _context = await Widgets.ContextAsync();
        }
        catch (ApiException)
        {
            // the pickers take a typed value
        }
    }

    private async Task SelectAsync(string name, bool keepAddress = false)
    {
        if (_running)
        {
            await ToCodeAsync();
        }
        await FlushAsync();
        try
        {
            _current = await Widgets.GetAsync(name);
        }
        catch (ApiException error)
        {
            _listError = error;
            return;
        }
        _code = _current.Code;
        _saved = _current.Prebuilt ? "Prebuilt: read-only" : string.Empty;
        if (!keepAddress)
        {
            Nav.NavigateTo($"widgets?name={Uri.EscapeDataString(name)}", replace: true);
        }
        await Js.InvokeVoidAsync("sab.setTitle", $"{name} · Widgets");
        _ = PrimeAsync(_current);
        if (await Js.InvokeAsync<string?>("sab.recall", $"widgets.view:{name}") == "preview")
        {
            await StartRunAsync(prompt: true, asked: false);
        }
    }

    /// <summary>The editor's intelligence over a kernel of its own in the widget's folder, primed with the widget
    /// runtime's names (sab_canvas, sab_widgets); no kernel: the server's Script over the folder.</summary>
    private async Task PrimeAsync(WidgetFull widget)
    {
        try
        {
            _kernel ??= (await Workbench.StartAsync(widget.KernelPath)).Kernel;
            await foreach (var _ in Workbench.RunAsync(_kernel, new RunRequest(widget.KernelSetup)))
            {
                // the setup prints nothing worth showing
            }
        }
        catch (ApiException)
        {
            _kernel = null;
        }
    }

    private IntelContext IntelOf()
    {
        var document = _current is { File.Length: > 0 } c ? c.File : $"{_current?.Name ?? "widget"}.widget.py";
        return new IntelContext(_kernel, _current?.KernelPath, null, false, [], [], document, null);
    }
}
