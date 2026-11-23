using Microsoft.AspNetCore.Components;
using Microsoft.AspNetCore.Components.Web;
using Microsoft.JSInterop;

namespace SwissArmyBench.Web.Pages.Canvas;

/// <summary>The board's pointer (the classic canvasPage.ts hook and the board's pointerdown): a press on a node selects
/// it (Shift, Ctrl: added or taken away) and drags it or its corner; a press on empty grid draws a container; the
/// frame's right edge previews another width. The pointer is captured on the board while it is down.</summary>
public partial class CanvasBoard
{
    private async Task NodeDownAsync(NodeDown down)
    {
        var e = down.Pointer;
        if (e.Button != 0)
        {
            return;
        }
        await _board.FocusAsync(preventScroll: true);
        var id = down.Node.Id;
        var additive = e.ShiftKey || e.CtrlKey || e.MetaKey;
        if (additive)
        {
            await OnSelect.InvokeAsync(View.Selected.Contains(id) ? View.Selected.Where(s => s != id).ToList() : [.. View.Selected, id]);
        }
        else if (!View.Selected.Contains(id))
        {
            await OnSelect.InvokeAsync([id]);
        }
        if (!View.Editable || additive || View.Find(id) is not { } at)
        {
            return;
        }
        await MeasureAsync(e.PointerId);
        var (x, y) = PagePoint(e.ClientX, e.ClientY);
        _drag = new Drag(at.Node, at.Parent, down.Sizing, x, y);
    }

    private async Task BoardDownAsync(PointerEventArgs e)
    {
        if (e.Button != 0 || View.State is null)
        {
            return;
        }
        await OnSelect.InvokeAsync([]);
        if (!View.Editable)
        {
            return;
        }
        await _board.FocusAsync(preventScroll: true);
        await MeasureAsync(e.PointerId);
        var (x, y) = PagePoint(e.ClientX, e.ClientY);
        var parent = View.ContainerAt(x, y, null);
        _band = new Band(x, y, parent, parent is null ? (0, 0) : View.Absolute(parent.Id), null);
    }

    private Task MoveAsync(PointerEventArgs e)
    {
        var (x, y) = PagePoint(e.ClientX, e.ClientY);
        if (_drag is { } drag)
        {
            DragTo(drag, x, y, e.AltKey);
        }
        else if (_band is { } band)
        {
            DrawTo(band, x, y, e.AltKey);
        }
        return Task.CompletedTask;
    }

    private void DragTo(Drag drag, double x, double y, bool alt)
    {
        var (dx, dy) = (x - drag.StartX, y - drag.StartY);
        if (_moved is null && Math.Abs(dx) + Math.Abs(dy) < DragThreshold / View.Zoom)
        {
            return;
        }
        var n = drag.Node;
        var raw = drag.Sizing ? new BoardRect(n.Id, n.X, n.Y, n.W + dx, n.H + dy) : new BoardRect(n.Id, n.X + dx, n.Y + dy, n.W, n.H);
        var done = CanvasGrid.Snap(raw, SnapFor(n.Id, drag.Parent, drag.Sizing, alt));
        _moved = done.Rect;
        _guides = done.Guides;
    }

    private void DrawTo(Band band, double x, double y, bool alt)
    {
        var raw = new BoardRect("new", Math.Min(band.StartX, x) - band.Origin.X, Math.Min(band.StartY, y) - band.Origin.Y, Math.Abs(x - band.StartX), Math.Abs(y - band.StartY));
        var placed = CanvasGrid.Snap(raw, SnapFor("new", band.Parent, false, alt)).Rect;
        var sized = CanvasGrid.Snap(placed with { Width = raw.Right - placed.Left, Height = raw.Bottom - placed.Top }, SnapFor("new", band.Parent, true, alt)).Rect;
        _band = band with { Made = sized };
    }

    private async Task UpAsync(PointerEventArgs e)
    {
        var (drag, band, moved) = (_drag, _band, _moved);
        (_drag, _band, _guides) = (null, null, []);
        if (band?.Made is { } made && made.Width >= SmallestDrawn && made.Height >= SmallestDrawn)
        {
            var body = new Dictionary<string, object?>
            {
                ["page"] = View.Page,
                ["parent"] = band.Parent?.Id,
                ["x"] = Math.Max(0, made.Left),
                ["y"] = Math.Max(0, made.Top),
                ["w"] = made.Width,
                ["h"] = made.Height,
            };
            if (await OnSend("add_container", body) is { Made: { } id })
            {
                await OnSelect.InvokeAsync([id]);
            }
        }
        if (drag is not null && moved is not null)
        {
            await DroppedAsync(drag, moved, PagePoint(e.ClientX, e.ClientY));
        }
        _moved = null;
    }

    /// <summary>A node let go: sized, or moved (dropped over another container: it goes in there).</summary>
    private async Task DroppedAsync(Drag drag, BoardRect r, (double X, double Y) point)
    {
        if (drag.Sizing)
        {
            await OnSend("move", new() { ["id"] = drag.Node.Id, ["w"] = Math.Max(1, r.Width), ["h"] = Math.Max(1, r.Height) });
            return;
        }
        var target = View.ContainerAt(point.X, point.Y, drag.Node.Id);
        if (target?.Id != drag.Parent?.Id && (target is not null || drag.Node.Kind == "container"))
        {
            var origin = target is null ? (0, 0) : View.Absolute(target.Id);
            var from = drag.Parent is null ? (0, 0) : View.Absolute(drag.Parent.Id);
            await OnSend("move", new()
            {
                ["id"] = drag.Node.Id,
                ["parent"] = target?.Id ?? string.Empty,
                ["x"] = Math.Max(0, CanvasGrid.Round(from.Item1 + r.Left - origin.Item1)),
                ["y"] = Math.Max(0, CanvasGrid.Round(from.Item2 + r.Top - origin.Item2)),
            });
            return;
        }
        await OnSend("move", new() { ["id"] = drag.Node.Id, ["x"] = Math.Max(0, r.Left), ["y"] = Math.Max(0, r.Top) });
    }

    private async Task WidthDownAsync(PointerEventArgs e)
    {
        var module = await ModuleAsync();
        await module.InvokeVoidAsync("capture", _handle, e.PointerId);
        _widthDrag = (e.ClientX, View.PreviewWidth[View.Layout]);
    }

    private void WidthMove(PointerEventArgs e)
    {
        if (_widthDrag is { } drag)
        {
            var (low, high) = View.Range;
            View.PreviewWidth[View.Layout] = CanvasGrid.Round(Math.Clamp(drag.From + ((e.ClientX - drag.StartX) / View.Zoom), low, high));
        }
    }

    private async Task WidthUpAsync()
    {
        if (_widthDrag is not null)
        {
            _widthDrag = null;
            await OnWidth.InvokeAsync();
        }
    }
}
