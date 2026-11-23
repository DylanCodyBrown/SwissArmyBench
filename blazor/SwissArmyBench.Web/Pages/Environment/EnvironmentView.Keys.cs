using Microsoft.AspNetCore.Components;
using Microsoft.AspNetCore.Components.Web;
using Microsoft.JSInterop;

namespace SwissArmyBench.Web.Pages.Environment;

/// <summary>The Environment's search box (the server's search once typing pauses) and its keys.</summary>
public partial class EnvironmentView
{
    private void SearchTyped(ChangeEventArgs e)
    {
        _typed = e.Value?.ToString() ?? string.Empty;
        _typing?.Cancel();
        _typing = new CancellationTokenSource();
        var token = _typing.Token;
        _ = InvokeAsync(async () =>
        {
            try
            {
                await Task.Delay(TypingPauseMilliseconds, token);
            }
            catch (TaskCanceledException)
            {
                return;
            }
            _query = _typed.Trim();
            await LoadAsync();
            StateHasChanged();
        });
    }

    /// <summary>The keys: Up, Down move; Right opens a level, Left closes; Enter opens; F2 renames; Delete removes;
    /// / goes to the search; Ctrl+B folds the viewer. Typing in a box keeps its keys.</summary>
    private async Task KeyAsync(KeyboardEventArgs e)
    {
        if ((e.CtrlKey || e.MetaKey) && e.Key.Equals("b", StringComparison.OrdinalIgnoreCase))
        {
            await FoldAsync();
            return;
        }
        if (_renaming is not null || _removing is not null || _clearing is not null || _installing || _menu is not null)
        {
            return;
        }
        var typing = await Js.InvokeAsync<bool>("sab.typing");
        if (e.Key == "/" && !typing)
        {
            await _searchBox.FocusAsync();
            return;
        }
        if (typing && e.Key != "ArrowDown" || e.CtrlKey || e.MetaKey || e.AltKey)
        {
            return;
        }
        await MoveAsync(e.Key);
    }

    private async Task MoveAsync(string key)
    {
        var shown = Rows(_tab);
        var at = shown.ToList().FindIndex(i => i.Id == _selected);
        var item = at >= 0 ? shown[at] : null;
        switch (key)
        {
            case "ArrowDown":
                _selected = shown.ElementAtOrDefault(Math.Min(shown.Count - 1, at + 1))?.Id ?? shown.FirstOrDefault()?.Id;
                break;
            case "ArrowUp":
                _selected = shown.ElementAtOrDefault(Math.Max(0, at - 1))?.Id;
                break;
            case "ArrowRight" when item is not null:
                await ToggleAsync(item, true);
                break;
            case "ArrowLeft" when item is not null:
                await ToggleAsync(item, false);
                break;
            case "Enter" when item is not null:
                await OpenItemAsync(item);
                return;
            case "F2" when item is not null:
                _renaming = item;
                return;
            case "Delete" when item is not null:
                _removing = item;
                return;
            default:
                return;
        }
        Moved();
        await Js.InvokeVoidAsync("sab.focus", ".env-row.sel");
    }
}
