using Microsoft.JSInterop;

using SwissArmyBench.Web.State;

namespace SwissArmyBench.Web.Pages.Canvas;

/// <summary>The Canvas following the server (the classic canvasPage.ts's onNotice): another window's change shown as
/// it is now, the widgets changed (the gallery and the previews again), a preview made, the theme's pictures.</summary>
public partial class CanvasPage
{
    private void OnNotice(Notice notice) => _ = InvokeAsync(() => HeardAsync(notice));

    private async Task HeardAsync(Notice notice)
    {
        switch (notice.Type)
        {
            case "canvas_changed" when _view.State is { } state && notice.Text("canvas") == state.Canvas && notice.Text("window") != Window:
                await ReloadAsync();
                Say("The canvas changed in another window: it is shown as it is now.");
                break;
            case FullNotice:
                await HeardFullAsync(notice);
                break;
            case "widgets_changed":
                _widgets = (await WidgetsApi.ListAsync()).Widgets;
                _previews.Clear();
                await ReloadAsync();
                break;
            case "widget_preview" or "widget_previews":
                _previews.Heard(notice.Type, notice.Text("name"), notice.Text("theme"));
                break;
            case "tables_changed" or "dataset_added" or "dataset_closed":
                _context = await WidgetsApi.ContextAsync();
                StateHasChanged();
                break;
            default:
                break;
        }
    }

    private void OnThemeChanged()
    {
        _previews.Theme = PreviewTheme;
        _ = InvokeAsync(StateHasChanged);
    }

    public async ValueTask DisposeAsync()
    {
        Live.NoticeArrived -= OnNotice;
        Theme.Changed -= OnThemeChanged;
        _dock.Changed -= OnDockChanged;
        Screen.Hide(this);
        _previews.Dispose();
        try
        {
            await LeaveFullAsync();
            if (_keys is not null)
            {
                await _keys.InvokeVoidAsync("stop");
                await _keys.DisposeAsync();
            }
            if (_module is not null)
            {
                await _module.DisposeAsync();
            }
        }
        catch (JSDisconnectedException)
        {
            // the page is closing
        }
        _self?.Dispose();
    }
}
