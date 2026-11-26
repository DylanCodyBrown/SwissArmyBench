using Microsoft.JSInterop;

using SwissArmyBench.Web.State;

namespace SwissArmyBench.Web.Pages.Canvas;

/// <summary>The Canvas full screen (the owner, 2026-11-26: "At full screen mode for the canvas"): F11 or the top bar's
/// button, the agent's canvas_full_screen (the canvas_full_screen notice). The rail, the status bar, the top bar, the
/// bottom bar and the panes go; the board fills the window with a small strip in its bottom left corner (Leave full
/// screen, Play, Undo and Redo, the zoom, and the Widgets and Properties panes as overlays). The same full screen as
/// the Notebooks and Scripts pages' F11 (shell.js sab.fullScreen: the desktop app's window, else the browser's
/// Fullscreen API, a refusal harmless). Left that way, the Canvas opens in it again (this browser).</summary>
public partial class CanvasPage
{
    public const string FullNotice = "canvas_full_screen";
    private const string FullKey = "canvas.full";
    private const string FullClass = "cvs-full";

    private bool _full;
    private string? _overlay;

    /// <summary>The dock's panes: none in full screen (the strip shows one over the board instead).</summary>
    private IReadOnlyList<SwissArmyBench.Web.Components.DockPane> ShownPanes => _full ? [] : DockPanes;

    private Task ToggleFullAsync() => SetFullAsync(!_full);

    private async Task SetFullAsync(bool on)
    {
        if (on == _full)
        {
            return;
        }
        _full = on;
        _overlay = null;
        StateHasChanged();
        await Js.InvokeVoidAsync("sab.fullScreen", on, FullClass);
        await Js.InvokeVoidAsync("sab.remember", FullKey, on ? "1" : "0");
    }

    /// <summary>The Canvas opens in full screen only when it was left that way.</summary>
    private async Task RecallFullAsync()
    {
        if (await Js.InvokeAsync<string?>("sab.recall", FullKey) == "1")
        {
            await SetFullAsync(true);
        }
    }

    /// <summary>The strip's Widgets and Properties: one pane over the board at a time, again to close it.</summary>
    private void ToggleOverlay(string pane) => _overlay = _overlay == pane ? null : pane;

    /// <summary>The agent's canvas_full_screen for the canvas this window holds (on, off, or none: the other way).</summary>
    private Task HeardFullAsync(Notice notice) => _view.State is { } state && notice.Text("canvas") == state.Canvas
        ? SetFullAsync(notice.Flag("on") ?? !_full)
        : Task.CompletedTask;

    /// <summary>The desktop app's F11 (the shell asks window.sabFullScreen first) and the browser's own Escape out of
    /// its full screen.</summary>
    [JSInvokable("FullScreen")]
    public Task FullScreenAsync(bool? on) => InvokeAsync(() => SetFullAsync(on ?? !_full));

    /// <summary>Leaving the page: the window and the body as they were.</summary>
    private async Task LeaveFullAsync()
    {
        if (_full)
        {
            await Js.InvokeVoidAsync("sab.fullScreen", false, FullClass);
        }
    }
}
