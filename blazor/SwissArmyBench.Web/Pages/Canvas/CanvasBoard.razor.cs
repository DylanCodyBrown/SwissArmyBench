using System.Globalization;

using Microsoft.AspNetCore.Components;
using Microsoft.AspNetCore.Components.Web;
using Microsoft.JSInterop;

using SwissArmyBench.Web.Api.Canvas;
using SwissArmyBench.Web.Api.Widgets;

namespace SwissArmyBench.Web.Pages.Canvas;

public partial class CanvasBoard
{
    // A press moves nothing until the pointer has gone this far (screen pixels); a drawn container is at least this.
    private const double DragThreshold = 3;
    private const double SmallestDrawn = 16;
    private const double SnapScreenPixels = 4;
    private const double LeastHeight = 600;
    private const double RoomBelow = 200;
    private const double ScalerRoom = 24;

    private ElementReference _viewport;
    private ElementReference _board;
    private ElementReference _handle;
    private IJSObjectReference? _module;
    private IJSObjectReference? _wheel;
    private DotNetObjectReference<CanvasBoard>? _self;
    private BoardBox _box = new(0, 0);
    private Drag? _drag;
    private Band? _band;
    private BoardRect? _moved;
    private IReadOnlyList<Guide> _guides = [];
    private (double StartX, double From)? _widthDrag;

    [Inject]
    private IJSRuntime Js { get; set; } = default!;

    [Parameter, EditorRequired]
    public CanvasView View { get; set; } = default!;

    [Parameter, EditorRequired]
    public IReadOnlyList<WidgetEntry> Widgets { get; set; } = [];

    [Parameter]
    public bool ShowWires { get; set; }

    /// <summary>The widget card being dragged from the Widgets pane (null: none).</summary>
    [Parameter]
    public string? Dragging { get; set; }

    [Parameter]
    public Func<string, Dictionary<string, object?>, Task<CanvasState?>> OnSend { get; set; } = default!;

    [Parameter]
    public EventCallback<IReadOnlyList<string>> OnSelect { get; set; }

    [Parameter]
    public EventCallback<OpenMenu> OnMenu { get; set; }

    [Parameter]
    public EventCallback<InsertRequest> OnInsert { get; set; }

    [Parameter]
    public EventCallback<string?> OnEditWidget { get; set; }

    [Parameter]
    public EventCallback<(double X, double Y, string Id)> OnReplace { get; set; }

    /// <summary>The preview width changed by the frame's edge (the page remembers it).</summary>
    [Parameter]
    public EventCallback OnWidth { get; set; }

    /// <summary>The run group every right-click menu ends with (after: a line above it).</summary>
    [Parameter]
    public Func<bool, IReadOnlyList<CanvasMenuItem>> RunGroup { get; set; } = _ => [];

    /// <summary>Ctrl+wheel over the viewport: the zoom times this factor.</summary>
    [Parameter]
    public EventCallback<double> OnWheel { get; set; }

    /// <summary>The viewport (Fit measures it).</summary>
    public ElementReference Viewport => _viewport;

    private CanvasSizing Sizing => View.State!.Model.Sizing;

    private SnapStep Step => Sizing.Snap ? SnapStep.From(Sizing.Step) : SnapStep.One;

    private double Height => View.Children.Select(c => c.Y + c.H + RoomBelow).Append(LeastHeight).Max();

    private string BoardStyle => FormattableString.Invariant(
        $"width: {View.PreviewWidth[View.Layout]}px; height: {Height}px; transform: scale({View.Zoom}); --dots: {CanvasGrid.DotSpacing(Step, View.Zoom)}px;");

    private string ScalerStyle => FormattableString.Invariant(
        $"width: {(View.PreviewWidth[View.Layout] + ScalerRoom) * View.Zoom}px; height: {Height * View.Zoom}px;");

    /// <summary>The grid's columns, drawn when snapping to the grid's cells.</summary>
    private IEnumerable<(double Left, double Width)> Columns => Sizing.Snap && Step.Grid
        ? CanvasGrid.Lines(View.PageWidth, Sizing.Columns, Sizing.Gap).Chunk(2).Select(pair => (View.X(pair[0]), View.X(pair[1] - pair[0])))
        : [];

    private static string Px(string name, double value) => string.Create(CultureInfo.InvariantCulture, $"{name}: {value}px; ");

    private string GuideStyle(Guide guide)
    {
        var parent = _drag?.Parent is { } p ? View.Absolute(p.Id) : (0, 0);
        return guide.Axis == "v"
            ? Px("left", View.X(parent.Item1 + guide.At)) + Px("top", parent.Item2 + guide.From) + Px("height", guide.To - guide.From)
            : Px("top", parent.Item2 + guide.At) + Px("left", View.X(parent.Item1 + guide.From)) + Px("width", View.X(guide.To - guide.From));
    }

    private string BandStyle(Band band) => band.Made is { } r
        ? Px("left", View.X(band.Origin.X + r.Left)) + Px("top", band.Origin.Y + r.Top) + Px("width", View.X(r.Width)) + Px("height", r.Height)
        : "display: none;";

    protected override async Task OnAfterRenderAsync(bool firstRender)
    {
        if (firstRender)
        {
            var module = await ModuleAsync();
            _self = DotNetObjectReference.Create(this);
            _wheel = await module.InvokeAsync<IJSObjectReference>("wheel", _viewport, _self);
        }
    }

    /// <summary>Ctrl+wheel (canvas.js wheel).</summary>
    [JSInvokable("Wheel")]
    public Task WheelAsync(double factor) => OnWheel.InvokeAsync(factor);

    private async Task<IJSObjectReference> ModuleAsync() => _module ??= await Js.InvokeAsync<IJSObjectReference>("import", "./js/canvas.js");

    /// <summary>The board's place on the screen, read as a press starts: a pointer's place in the page's pixels.</summary>
    private async Task MeasureAsync(long pointer)
    {
        var module = await ModuleAsync();
        _box = await module.InvokeAsync<BoardBox>("rect", _board);
        await module.InvokeVoidAsync("capture", _board, pointer);
    }

    private (double X, double Y) PagePoint(double clientX, double clientY) =>
        ((clientX - _box.Left) / View.Zoom / View.Stretch, (clientY - _box.Top) / View.Zoom);

    private SnapSettings SnapFor(string id, CanvasNode? parent, bool sizing, bool alt)
    {
        var siblings = parent?.Children ?? View.Children;
        var others = siblings.Where(o => o.Id != id).Select(o => new BoardRect(o.Id, o.X, o.Y, o.W, o.H)).ToList();
        return new SnapSettings(Sizing.Snap && !alt, Sizing.Snap ? SnapStep.From(Sizing.Step) : SnapStep.One, View.GridFor(parent), others, SnapScreenPixels / View.Zoom / View.Stretch, sizing);
    }

    private async Task RemoveAsync(string id) => await OnSend("delete", new() { ["id"] = id });

    private async Task DropAsync(DragEventArgs e)
    {
        if (Dragging is not { } widget)
        {
            return;
        }
        var module = await ModuleAsync();
        _box = await module.InvokeAsync<BoardBox>("rect", _board);
        var (x, y) = PagePoint(e.ClientX, e.ClientY);
        await OnInsert.InvokeAsync(new InsertRequest(widget, null, CanvasGrid.Round(x), CanvasGrid.Round(y)));
    }

    private async Task NodeDropAsync(NodeDrop drop)
    {
        if (Dragging is not { } widget || drop.Node.Kind != "container")
        {
            return;
        }
        var module = await ModuleAsync();
        _box = await module.InvokeAsync<BoardBox>("rect", _board);
        var (x, y) = PagePoint(drop.ClientX, drop.ClientY);
        var origin = View.Absolute(drop.Node.Id);
        await OnInsert.InvokeAsync(new InsertRequest(widget, drop.Node.Id, Math.Max(0, CanvasGrid.Round(x - origin.X)), Math.Max(0, CanvasGrid.Round(y - origin.Y))));
    }

    public async ValueTask DisposeAsync()
    {
        _self?.Dispose();
        if (_module is not null)
        {
            try
            {
                if (_wheel is not null)
                {
                    await _wheel.InvokeVoidAsync("stop");
                    await _wheel.DisposeAsync();
                }
                await _module.DisposeAsync();
            }
            catch (JSDisconnectedException)
            {
                // the page is closing
            }
        }
    }
}
