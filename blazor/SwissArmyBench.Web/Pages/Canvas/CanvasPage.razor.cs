
using Microsoft.AspNetCore.Components;
using Microsoft.JSInterop;

using SwissArmyBench.Web.Api;
using SwissArmyBench.Web.Api.Canvas;
using SwissArmyBench.Web.Api.Widgets;
using SwissArmyBench.Web.Components;
using SwissArmyBench.Web.State;

namespace SwissArmyBench.Web.Pages.Canvas;

public partial class CanvasPage
{
    // A notice stays this long, then goes (unless another replaced it).
    private const int NoticeMs = 8000;

    // Another window changed the canvas meanwhile (the server's 409).
    private const int Conflict = 409;

    private readonly CanvasView _view = new();
    private WidgetPreviews _previews = default!;
    private IReadOnlyList<WidgetEntry> _widgets = [];
    private WidgetContext? _context;
    private CanvasBoard? _board;
    private GalleryPane? _gallery;
    private bool _loading = true;
    private string? _opened;
    private bool _showWires;
    private PaneDockState _dock = default!;
    private OpenMenu? _menu;
    private (double X, double Y, string Id)? _replacing;
    private bool _buildsOpen;
    private bool _sharing;
    private string _notice = string.Empty;
    private Exception? _error;
    private string? _warning;
    private IJSObjectReference? _module;
    private IJSObjectReference? _keys;
    private DotNetObjectReference<CanvasPage>? _self;

    [Inject]
    private CanvasClient Canvases { get; set; } = default!;

    [Inject]
    private WidgetsClient WidgetsApi { get; set; } = default!;

    [Inject]
    private LiveUpdates Live { get; set; } = default!;

    [Inject]
    private ThemeState Theme { get; set; } = default!;

    [Inject]
    private PackagePrompts Prompts { get; set; } = default!;

    [Inject]
    private Notes Notes { get; set; } = default!;

    [Inject]
    private NavigationManager Nav { get; set; } = default!;

    [Inject]
    private IJSRuntime Js { get; set; } = default!;

    [Inject]
    private SwissArmyBench.Web.Api.Files.FileChooser Files { get; set; } = default!;

    [SupplyParameterFromQuery(Name = "path")]
    public string? Path { get; set; }

    private string Window => ApiClient.ClientId;

    protected override void OnInitialized()
    {
        _previews = new WidgetPreviews(WidgetsApi) { Theme = PreviewTheme, OnMissing = AskInstallAsync };
        _dock = new PaneDockState(Js, DockKey, _defaultDock);
        _dock.Changed += OnDockChanged;
        Live.NoticeArrived += OnNotice;
        Theme.Changed += OnThemeChanged;
    }

    /// <summary>A canvas named in the address (again: New canvas on the landing goes to it).</summary>
    protected override async Task OnParametersSetAsync()
    {
        if (Path is null || Path == _opened)
        {
            return;
        }
        _opened = Path;
        _loading = true;
        _showWires = await Js.InvokeAsync<string?>("sab.recall", "canvas.wires") == "1";
        try
        {
            var listing = WidgetsApi.ListAsync();
            var context = WidgetsApi.ContextAsync();
            _widgets = (await listing).Widgets;
            _context = await context;
            await TakeFirstAsync(await Canvases.OpenAsync(Path));
        }
        catch (ApiException error)
        {
            _error = error;
        }
        _loading = false;
        if (_keys is null)
        {
            await StartKeysAsync();
            await RecallFullAsync();
        }
        await DoAskedAsync();
    }

    /// <summary>The page's keys and the zoom's wheel, once a canvas is open.</summary>
    private async Task StartKeysAsync()
    {
        _module = await Js.InvokeAsync<IJSObjectReference>("import", "./js/canvas.js");
        _self = DotNetObjectReference.Create(this);
        _keys = await _module.InvokeAsync<IJSObjectReference>("keys", _self);
    }

    private string PreviewTheme => Theme.IsDark ? "dark" : "light";

    private bool Running => _playUrl is not null || _launched;

    /// <summary>The first state of a canvas: the panes, the zoom and the layout it was left with, then drawn.</summary>
    private async Task TakeFirstAsync(CanvasState state)
    {
        await _dock.LoadAsync();
        var kept = await RecallAsync<KeptView>($"canvas.view:{state.Path}");
        if (kept is not null)
        {
            _view.Layout = kept.Layout is CanvasView.Phone ? CanvasView.Phone : CanvasView.Desktop;
            _view.PreviewWidth[CanvasView.Desktop] = kept.Desktop;
            _view.PreviewWidth[CanvasView.Phone] = kept.Phone;
            _view.SetZoom(kept.Zoom);
        }
        await Js.InvokeVoidAsync("sab.setTitle", $"{state.Name} · Canvas");
        Take(state);
    }

    /// <summary>The server's answer drawn: the page in front kept when it is still there, the selection pruned.</summary>
    private void Take(CanvasState state)
    {
        _view.State = state;
        if (!state.Model.Pages.Any(p => p.Id == _view.Page))
        {
            _view.Page = state.Model.Pages.FirstOrDefault()?.Id ?? string.Empty;
        }
        _view.Selected = _view.Selected.Where(id => _view.Find(id) is not null).ToList();
        if (state.Notes.Count > 0)
        {
            Say(string.Join(' ', state.Notes));
        }
        StateHasChanged();
    }

    /// <summary>One change on the version this window holds; another window's change meanwhile: the canvas as it is
    /// now, and the words to do it again.</summary>
    private async Task<CanvasState?> SendAsync(string kind, Dictionary<string, object?> body)
    {
        if (_view.State is not { } state)
        {
            return null;
        }
        var sent = new Dictionary<string, object?>(body)
        {
            ["kind"] = kind,
            ["version"] = state.Version,
            ["window"] = Window,
            ["layout"] = _view.Layout,
        };
        try
        {
            var after = await Canvases.CommandAsync(state.Canvas, sent);
            Take(after);
            return after;
        }
        catch (ApiException error) when (error.Status == Conflict)
        {
            await ReloadAsync();
            Say(error.Refusal.Error.Length > 0 ? error.Refusal.Error : "The canvas changed: it is shown as it is now. Do it again.");
        }
        catch (ApiException error)
        {
            _error = error;
            StateHasChanged();
        }
        return null;
    }

    /// <summary>An In's source or an Event's actions; refused in place with the server's reason.</summary>
    private async Task WireAsync(WireChange change)
    {
        if (_view.State is not { } state)
        {
            return;
        }
        var body = new Dictionary<string, object?>
        {
            ["kind"] = "wire",
            ["id"] = change.Id,
            ["port"] = change.Port,
            ["wire"] = change.Wire,
            ["version"] = state.Version,
            ["window"] = Window,
        };
        try
        {
            Take(await Canvases.CommandAsync(state.Canvas, body));
        }
        catch (ApiException error) when (error.Status == Conflict)
        {
            await ReloadAsync();
            throw;
        }
    }

    private async Task ReloadAsync()
    {
        if (_view.State is { } state)
        {
            Take(await Canvases.StateAsync(state.Canvas));
        }
    }

    private void Say(string words)
    {
        _notice = words;
        StateHasChanged();
        _ = ForgetSoonAsync(words);
    }

    private async Task ForgetSoonAsync(string words)
    {
        await Task.Delay(NoticeMs);
        if (_notice == words)
        {
            _notice = string.Empty;
            await InvokeAsync(StateHasChanged);
        }
    }

    private void ClearError()
    {
        _error = null;
        _warning = null;
    }

    private void SelectPage(string page)
    {
        _view.Page = page;
        _view.Selected = [];
    }

    private void Select(IReadOnlyList<string> ids) => _view.Selected = ids.ToList();

    private void OpenMenu(OpenMenu menu) => _menu = menu;

    private void CloseMenu() => _menu = null;

    private void ReplaceAt((double X, double Y, string Id) at) => _replacing = at;

    private async Task ReplaceAsync(string widget)
    {
        if (_replacing is { } at)
        {
            _replacing = null;
            await SendAsync("replace_widget", new() { ["id"] = at.Id, ["widget"] = widget });
        }
    }

    private async Task InsertAsync(InsertRequest request)
    {
        var body = new Dictionary<string, object?> { ["page"] = _view.Page, ["widget"] = request.Widget, ["parent"] = request.Parent };
        if (request.X is { } x && request.Y is { } y)
        {
            body["x"] = x;
            body["y"] = y;
        }
        if (await SendAsync("insert_widget", body) is { Made: { } made })
        {
            _view.Selected = [made];
        }
    }

    private Task InsertSelectedAsync(string widget) => InsertAsync(new InsertRequest(widget, _view.SelectedContainer(), null, null));

    private async Task OpenWidgetsAsync(string? widget)
    {
        var address = widget is null ? "widgets" : $"widgets?name={Uri.EscapeDataString(widget)}";
        await Js.InvokeAsync<bool>("open", Nav.ToAbsoluteUri(address).ToString(), "sab-widgets");
    }
}
