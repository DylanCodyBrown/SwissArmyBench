using Microsoft.JSInterop;

using SwissArmyBench.Web.Api;

namespace SwissArmyBench.Web.Pages.Canvas;

/// <summary>The Canvas's keys and its view (the classic canvasPage.ts's keydown and zoom): F5 Play, Ctrl+F5 Launch,
/// Ctrl+Shift+F5 with the analyzer, Ctrl+Shift+E Export; Ctrl+Z, Ctrl+Y, Ctrl+= and -, Ctrl+0; Escape; Delete;
/// Insert; the arrows nudge by the step (Shift: ten steps, Alt: one pixel). Undo and Redo, the zoom, the layout, the
/// panes and the Wiring view.</summary>
public partial class CanvasPage
{
    private const double ZoomStep = 1.25;
    private const double FitMargin = 48;

    private static readonly IReadOnlyDictionary<string, (int X, int Y)> _arrows = new Dictionary<string, (int X, int Y)>
    {
        ["ArrowLeft"] = (-1, 0),
        ["ArrowRight"] = (1, 0),
        ["ArrowUp"] = (0, -1),
        ["ArrowDown"] = (0, 1),
    };

    /// <summary>A key of the page (canvas.js keys): typing is true when a box had the focus (Escape only).</summary>
    [JSInvokable("Key")]
    public async Task KeyAsync(string key, bool ctrl, bool shift, bool alt, bool typing)
    {
        if (_view.State is null)
        {
            return;
        }
        if (await RunKeyAsync(key, ctrl, shift) || typing)
        {
            StateHasChanged();
            return;
        }
        if (ctrl && !alt)
        {
            await CtrlKeyAsync(key.ToLowerInvariant(), shift);
        }
        else if (key == "Escape")
        {
            _menu = null;
            _replacing = null;
            if (_playUrl is not null)
            {
                await StopPlayAsync();
            }
            else
            {
                _view.Selected = [];
            }
        }
        else if (_view.Editable)
        {
            await EditKeyAsync(key, shift, alt);
        }
        StateHasChanged();
    }

    /// <summary>Ctrl+wheel over the viewport (the board tells it).</summary>
    private Task WheelAsync(double factor) => SetZoomAsync(_view.Zoom * factor);

    private async Task<bool> RunKeyAsync(string key, bool ctrl, bool shift)
    {
        if (key == "F5")
        {
            await (ctrl ? LaunchAsync(shift) : PlayAsync());
            return true;
        }
        if (ctrl && shift && key.Equals("e", StringComparison.OrdinalIgnoreCase))
        {
            await ExportAsync();
            return true;
        }
        return false;
    }

    private async Task CtrlKeyAsync(string key, bool shift)
    {
        switch (key)
        {
            case "z":
                await UndoAsync(shift);
                break;
            case "y":
                await UndoAsync(true);
                break;
            case "=" or "+":
                await SetZoomAsync(_view.Zoom * ZoomStep);
                break;
            case "-":
                await SetZoomAsync(_view.Zoom / ZoomStep);
                break;
            case "0":
                await SetZoomAsync(1);
                break;
            default:
                break;
        }
    }

    private async Task EditKeyAsync(string key, bool shift, bool alt)
    {
        if (key is "Delete" or "Backspace" && _view.Selected.Count > 0)
        {
            var ids = _view.Selected.ToList();
            _view.Selected = [];
            foreach (var id in ids.Where(id => _view.Find(id) is not null))
            {
                await SendAsync("delete", new() { ["id"] = id });
            }
            return;
        }
        if (key == "Insert" && _gallery?.Focused is { } focused)
        {
            await InsertSelectedAsync(focused);
            return;
        }
        if (_arrows.TryGetValue(key, out var arrow) && _view.Selected.Count == 1 && _view.Find(_view.Selected[0]) is { } at)
        {
            var sizing = _view.State!.Model.Sizing;
            var step = sizing.Snap ? SnapStep.From(sizing.Step) : SnapStep.One;
            var by = CanvasGrid.NudgeBy(step, shift, alt, _view.GridFor(at.Parent));
            await SendAsync("move", new()
            {
                ["id"] = at.Node.Id,
                ["x"] = Math.Max(0, at.Node.X + (arrow.X * by)),
                ["y"] = Math.Max(0, at.Node.Y + (arrow.Y * by)),
            });
        }
    }

    private async Task UndoAsync(bool redo)
    {
        if (_view.State is not { } state || !_view.Editable)
        {
            return;
        }
        try
        {
            Take(await Canvases.UndoAsync(state.Canvas, redo, Window));
        }
        catch (ApiException error)
        {
            _error = error;
        }
    }

    private Task SetZoomAsync(double zoom)
    {
        _view.SetZoom(zoom);
        StateHasChanged();
        return RememberViewAsync();
    }

    private async Task FitAsync()
    {
        if (_board is not null && _module is not null)
        {
            var width = await _module.InvokeAsync<double>("width", _board.Viewport);
            await SetZoomAsync((width - FitMargin) / _view.PreviewWidth[_view.Layout]);
        }
    }

    private Task SetLayoutAsync(string layout)
    {
        _view.Layout = layout;
        _view.Selected = _view.Selected.Where(id => _view.Find(id) is not null).ToList();
        return RememberViewAsync();
    }

    private Task RememberViewAsync() => _view.State is { } state
        ? RememberAsync($"canvas.view:{state.Path}", new KeptView(_view.Layout, _view.PreviewWidth[CanvasView.Desktop], _view.PreviewWidth[CanvasView.Phone], _view.Zoom))
        : Task.CompletedTask;

    private Task ToggleWiresAsync()
    {
        _showWires = !_showWires;
        return Js.InvokeVoidAsync("sab.remember", "canvas.wires", _showWires ? "1" : "0").AsTask();
    }

    private Task TogglePaneAsync(string pane)
    {
        _panes = pane == "properties" ? _panes with { Properties = !_panes.Properties } : _panes with { Widgets = !_panes.Widgets };
        return RememberPanesAsync();
    }

    private Task PaneWidthAsync(string pane, double width)
    {
        _panes = pane == "properties" ? _panes with { PropertiesWidth = width } : _panes with { WidgetsWidth = width };
        return RememberPanesAsync();
    }

    private Task RememberPanesAsync() => _view.State is { } state ? RememberAsync($"canvas.panes:{state.Path}", _panes) : Task.CompletedTask;
}
