using Microsoft.AspNetCore.Components;
using Microsoft.AspNetCore.Components.Web;

using SwissArmyBench.Web.Api;
using SwissArmyBench.Web.Api.Files;

namespace SwissArmyBench.Web.Components;

/// <summary>The page's own file picker's keys and New folder (the classic fileChooser.ts): the filter's arrows, Enter
/// and Escape; the list's arrows, Home, End, Enter and Backspace; the path box's and File name's Enter; New folder's
/// name, Enter to make it and Escape to put it away.</summary>
public partial class FilePicker
{
    private void FilterTyped(ChangeEventArgs e)
    {
        _filter = e.Value?.ToString() ?? string.Empty;
        _selected = -1;
    }

    private async Task FilterKeyAsync(KeyboardEventArgs e)
    {
        switch (e.Key)
        {
            case "ArrowDown" or "Enter":
                Select(0);
                if (e.Key == "Enter" && Drawn.Count == 1)
                {
                    await ActivateAsync(0);
                }
                break;
            case "Escape" when _filter.Length > 0:
                _filter = string.Empty;
                break;
            case "Escape":
                // The filter's keys stop at it (the markup's stopPropagation): an empty filter's Escape is the dialog's.
                await FinishAsync(null);
                break;
            default:
                break;
        }
    }

    private async Task ListKeyAsync(KeyboardEventArgs e)
    {
        switch (e.Key)
        {
            case "ArrowDown":
                Select(_selected + 1);
                break;
            case "ArrowUp":
                Select(_selected < 0 ? 0 : _selected - 1);
                break;
            case "Home":
                Select(0);
                break;
            case "End":
                Select(Drawn.Count - 1);
                break;
            case "Enter" when _selected >= 0:
                await ActivateAsync(_selected);
                break;
            case "Enter" when Request.Mode != "file":
                await PickAsync();
                break;
            case "Backspace" when !_naming:
                await UpAsync();
                break;
            default:
                break;
        }
    }

    private async Task WhereKeyAsync(KeyboardEventArgs e)
    {
        if (e.Key == "Enter")
        {
            await GoAsync(_where.Trim());
        }
    }

    private async Task SaveKeyAsync(KeyboardEventArgs e)
    {
        if (e.Key == "Enter")
        {
            await PickAsync();
        }
    }

    private void NewFolder()
    {
        if (_shown is null || _naming)
        {
            return;
        }
        _naming = true;
        _newName = "New folder";
        _ = FocusNewAsync();
    }

    private async Task FocusNewAsync()
    {
        await Task.Yield();
        await _newBox.FocusAsync();
    }

    private async Task NewFolderKeyAsync(KeyboardEventArgs e)
    {
        switch (e.Key)
        {
            case "Enter":
                await MakeFolderAsync();
                break;
            case "Escape":
                _naming = false;
                _focusList = true;
                break;
            default:
                break;
        }
    }

    private async Task MakeFolderAsync()
    {
        if (_shown is not { } at)
        {
            return;
        }
        try
        {
            var made = await Api.PostAsync<FolderMade>("/folders/new", new { path = at.Path, name = _newName });
            _naming = false;
            await GoAsync(made.Path);
            if (Request.Mode == "save")
            {
                await _saveBox.FocusAsync();
            }
            else
            {
                _focusList = true;
            }
        }
        catch (ApiException error)
        {
            _status = error.Message;
        }
    }
}
