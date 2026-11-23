using Microsoft.JSInterop;

using SwissArmyBench.Web.Api;
using SwissArmyBench.Web.Api.Widgets;
using SwissArmyBench.Web.State;

namespace SwissArmyBench.Web.Pages.Widgets;

/// <summary>The Widgets window following its Properties and the server: a property written into the code, a rename,
/// a delete; another window's or the agent's change shown as it is now (while it is not being typed in); the
/// pickers' tables again as tables open and close.</summary>
public partial class WidgetsPage
{
    /// <summary>A property's default written into the code (its own characters only): the editor takes the code.</summary>
    private async Task SavedAsync(WidgetFull after)
    {
        _current = after;
        _code = after.Code;
        _saved = "Saved";
        if (_running)
        {
            await RunAsync();
        }
    }

    private async Task RenamedAsync(WidgetFull after)
    {
        var before = _current?.Name;
        if (before is not null && after.Name != before)
        {
            var view = await Js.InvokeAsync<string?>("sab.recall", $"widgets.view:{before}");
            await Js.InvokeVoidAsync("sab.remember", $"widgets.view:{after.Name}", view ?? "code");
        }
        _current = after with { Code = _code };
        Nav.NavigateTo($"widgets?name={Uri.EscapeDataString(after.Name)}", replace: true);
        await Js.InvokeVoidAsync("sab.setTitle", $"{after.Name} · Widgets");
        await LoadListAsync();
    }

    private async Task DeletedAsync()
    {
        _current = null;
        await LoadListAsync();
        if (_widgets?.FirstOrDefault() is { } first)
        {
            await SelectAsync(first.Name);
        }
    }

    private void OnNotice(Notice notice) => _ = InvokeAsync(() => HeardAsync(notice));

    private async Task HeardAsync(Notice notice)
    {
        if (notice.Type == "widgets_changed")
        {
            await LoadListAsync();
            var name = notice.Text("name");
            var old = notice.Text("old");
            var mine = _current is { } c && (name == c.Name || old == c.Name);
            if (mine && name is not null && _saveWait is null)
            {
                await SelectAsync(name, keepAddress: true);
            }
            StateHasChanged();
        }
        else if (notice.Type is "tables_changed" or "dataset_added" or "dataset_closed")
        {
            await LoadContextAsync();
            StateHasChanged();
        }
    }

    public async ValueTask DisposeAsync()
    {
        Live.NoticeArrived -= OnNotice;
        await FlushAsync();
        try
        {
            await Widgets.StopAsync(Window);
        }
        catch (ApiException)
        {
            // nothing was running
        }
        try
        {
            if (_keys is not null)
            {
                await _keys.InvokeVoidAsync("stop");
                await _keys.DisposeAsync();
            }
        }
        catch (JSDisconnectedException)
        {
            // the page is closing
        }
        _self?.Dispose();
    }
}
