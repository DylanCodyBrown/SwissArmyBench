using System.Globalization;

using Microsoft.AspNetCore.Components;
using Microsoft.AspNetCore.Components.Web;
using Microsoft.JSInterop;

namespace SwissArmyBench.Web.Components;

public partial class PaneDock
{
    // The arrow keys move a side's grip and the line between stacked panes by these steps.
    private const double WidthKeyStep = 16;
    private const double ShareKeyStep = 0.05;

    private static readonly DockSide[] _sides = [DockSide.Left, DockSide.Right];

    private readonly Dictionary<string, ElementReference> _paneRefs = [];
    private readonly Dictionary<string, ElementReference> _lineRefs = [];
    private (string Title, IReadOnlyList<MenuEntry> Entries, double X, double Y)? _menu;
    private string? _dragging;
    private DockSide? _over;
    private (DockSide Side, double From, double Start)? _widthDrag;
    private (DockSide Side, int Upper, double Top, double Height)? _splitDrag;
    private double? _liveWidth;
    private PaneDockState? _listening;

    [Inject]
    private IJSRuntime Js { get; set; } = default!;

    /// <summary>The page's dock: where each pane is, and what moves them.</summary>
    [Parameter, EditorRequired]
    public PaneDockState State { get; set; } = default!;

    /// <summary>Every pane the page has (the layout says which side each is on and whether it shows).</summary>
    [Parameter, EditorRequired]
    public IReadOnlyList<DockPane> Panes { get; set; } = [];

    /// <summary>The page's own work, between the two sides.</summary>
    [Parameter]
    public RenderFragment? ChildContent { get; set; }

    [Parameter]
    public string? ClassName { get; set; }

    private static IReadOnlyList<DockSide> Sides => _sides;

    private DockLayout Layout => State.Layout;

    protected override void OnParametersSet()
    {
        if (!ReferenceEquals(_listening, State))
        {
            if (_listening is not null)
            {
                _listening.Changed -= OnChanged;
            }
            _listening = State;
            _listening.Changed += OnChanged;
        }
    }

    public void Dispose()
    {
        if (_listening is not null)
        {
            _listening.Changed -= OnChanged;
        }
    }

    private void OnChanged() => InvokeAsync(StateHasChanged);

    private static string Word(DockSide side) => side == DockSide.Left ? "left" : "right";

    private static string Px(double value) => value.ToString("0.#", CultureInfo.InvariantCulture);

    /// <summary>The panes shown on a side, each with its content (a pane the page did not hand over is left out).</summary>
    private IReadOnlyList<(DockSpot Spot, DockPane Pane)> Shown(DockSide side) =>
        Layout.On(side).Join(Panes, s => s.Id, p => p.Id, (s, p) => (s, p)).ToList();

    private double WidthOf(DockSide side) => _widthDrag?.Side == side && _liveWidth is { } live ? live : Layout.Width(side);

    /// <summary>The pane's menu: the other side to move it to, and Hide.</summary>
    private void OpenMenu(DockPane pane, MouseEventArgs e)
    {
        var side = Layout.SideOf(pane.Id);
        IReadOnlyList<MenuEntry> entries =
        [
            new("Move to left", "back", () => State.MoveAsync(pane.Id, DockSide.Left), side == DockSide.Left ? "It is on the left." : null),
            new("Move to right", "forward", () => State.MoveAsync(pane.Id, DockSide.Right), side == DockSide.Right ? "It is on the right." : null),
            MenuEntry.Separator,
            new($"Hide {pane.Label}", "eye-off", () => State.HideAsync(pane.Id)),
        ];
        _menu = (pane.Label, entries, e.ClientX, e.ClientY);
    }

    private async Task DropAsync(DockSide side)
    {
        var id = _dragging;
        (_dragging, _over) = (null, null);
        if (id is not null && Layout.SideOf(id) != side)
        {
            await State.MoveAsync(id, side);
        }
    }

    private async Task WidthDownAsync(PointerEventArgs e, DockSide side)
    {
        _widthDrag = (side, Layout.Width(side), e.ClientX);
        _liveWidth = Layout.Width(side);
        var module = await Js.InvokeAsync<IJSObjectReference>("import", "./js/canvas.js");
        await module.InvokeVoidAsync("capture", _lineRefs[GripKey(side)], e.PointerId);
    }

    // The left side's grip is on its right edge (dragging right makes it wider); the right side's on its left.
    private void WidthMove(PointerEventArgs e)
    {
        if (_widthDrag is { } drag)
        {
            var moved = e.ClientX - drag.Start;
            _liveWidth = Math.Clamp(drag.From + (drag.Side == DockSide.Left ? moved : -moved), DockLayout.Narrowest, DockLayout.Widest);
        }
    }

    private async Task WidthUpAsync()
    {
        if (_widthDrag is { } drag && _liveWidth is { } width)
        {
            (_widthDrag, _liveWidth) = (null, null);
            await State.WidthAsync(drag.Side, width);
        }
        (_widthDrag, _liveWidth) = (null, null);
    }

    private Task WidthKeyAsync(KeyboardEventArgs e, DockSide side)
    {
        var wider = side == DockSide.Left ? "ArrowRight" : "ArrowLeft";
        var narrower = side == DockSide.Left ? "ArrowLeft" : "ArrowRight";
        var by = e.Key == wider ? WidthKeyStep : e.Key == narrower ? -WidthKeyStep : 0;
        return by == 0 ? Task.CompletedTask : State.WidthAsync(side, Layout.Width(side) + by);
    }

    /// <summary>The line between two stacked panes taken: their two boxes' top and height, so the pointer's place
    /// is the upper one's share.</summary>
    private async Task SplitDownAsync(PointerEventArgs e, DockSide side, int upper)
    {
        var shown = Shown(side);
        if (upper + 1 >= shown.Count)
        {
            return;
        }
        var module = await Js.InvokeAsync<IJSObjectReference>("import", "./js/canvas.js");
        var top = await module.InvokeAsync<DockBox>("rect", _paneRefs[shown[upper].Pane.Id]);
        var bottom = await module.InvokeAsync<DockBox>("rect", _paneRefs[shown[upper + 1].Pane.Id]);
        _splitDrag = (side, upper, top.Top, bottom.Top + bottom.Height - top.Top);
        await module.InvokeVoidAsync("capture", _lineRefs[SplitKey(side, upper)], e.PointerId);
    }

    private Task SplitMoveAsync(PointerEventArgs e) => _splitDrag is { Height: > 0 } drag
        ? State.SplitAsync(drag.Side, drag.Upper, (e.ClientY - drag.Top) / drag.Height)
        : Task.CompletedTask;

    private Task SplitKeyAsync(KeyboardEventArgs e, DockSide side, int upper)
    {
        var by = e.Key switch { "ArrowUp" => -ShareKeyStep, "ArrowDown" => ShareKeyStep, _ => 0 };
        return by == 0 ? Task.CompletedTask : State.SplitAsync(side, upper, Layout.Share(side, upper) + by);
    }

    private static string GripKey(DockSide side) => $"grip-{Word(side)}";

    private static string SplitKey(DockSide side, int upper) => $"split-{Word(side)}-{upper}";
}
