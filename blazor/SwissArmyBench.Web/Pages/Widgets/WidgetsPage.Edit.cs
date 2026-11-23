using System.Text.RegularExpressions;

using Microsoft.JSInterop;

using SwissArmyBench.Web.Api;
using SwissArmyBench.Web.Api.Widgets;
using SwissArmyBench.Web.Components;

namespace SwissArmyBench.Web.Pages.Widgets;

/// <summary>The Widgets window's editing (the classic widgetPage.ts): the code saved as it is typed, the properties
/// read again live, Code | Preview (the widget run alone, its errors headless with a link to the line), New widget,
/// Copy as your own and Copy to project or library, the list folded, Properties shown or hidden, the keys.</summary>
public partial class WidgetsPage
{
    private async Task CodeChangedAsync(string code)
    {
        _code = code;
        if (_current is null)
        {
            return;
        }
        if (!_current.Prebuilt)
        {
            _saved = "Saving…";
            _saveWait?.Cancel();
            _saveWait = new CancellationTokenSource();
            _ = RunLaterAsync(_saveWait.Token, SaveMs, SaveAsync);
        }
        _propsWait?.Cancel();
        _propsWait = new CancellationTokenSource();
        _ = RunLaterAsync(_propsWait.Token, LivePropertiesMs, LivePropertiesAsync);
        await Task.CompletedTask;
    }

    private static async Task RunLaterAsync(CancellationToken token, int ms, Func<Task> work)
    {
        try
        {
            await Task.Delay(ms, token);
        }
        catch (TaskCanceledException)
        {
            return;
        }
        await work();
    }

    /// <summary>The code saved below its header (never a prebuilt one).</summary>
    private async Task SaveAsync()
    {
        _saveWait = null;
        if (_current is not { Prebuilt: false } widget)
        {
            return;
        }
        try
        {
            var after = await Widgets.SaveAsync(widget.Name, _code);
            if (_current?.Name == after.Name)
            {
                _current = after with { Code = _code };
                _saved = "Saved";
            }
        }
        catch (ApiException error)
        {
            _saved = "Not saved";
            _listError = error;
        }
        await InvokeAsync(StateHasChanged);
    }

    /// <summary>A save waiting is done now (another widget chosen, a property written, the page left).</summary>
    private async Task FlushAsync()
    {
        if (_saveWait is { } wait)
        {
            wait.Cancel();
            await SaveAsync();
        }
    }

    private async Task LivePropertiesAsync()
    {
        if (_current is null)
        {
            return;
        }
        try
        {
            var found = await Widgets.PropertiesAsync(_code);
            _current = _current with { Properties = found.Properties, Contract = found.Contract, Problem = found.Problem };
            await InvokeAsync(StateHasChanged);
        }
        catch (ApiException)
        {
            // the pane keeps what it showed
        }
    }

    /// <summary>Preview (F5): the widget run alone in the editor's place; a failure's error panel there, its line
    /// linked to the code.</summary>
    private async Task RunAsync()
    {
        if (_current is not { } widget)
        {
            return;
        }
        var code = _editor is null ? _code : await _editor.TextAsync();
        (_running, _starting, _failed, _failedLine, _frame) = (true, true, null, null, null);
        RunStarted(widget.Name);
        await Js.InvokeVoidAsync("sab.remember", $"widgets.view:{widget.Name}", "preview");
        StateHasChanged();
        try
        {
            var said = await Widgets.RunAsync(widget.Name, code, Window);
            if (!_running || _current != widget)
            {
                return;
            }
            if (!said.Ok || said.Url is null)
            {
                var words = said.Problem?.Message ?? (said.Problem?.Kind == "missing" ? $"Streamlit widgets need {said.Problem.Command ?? "Streamlit"} in this Python." : "The widget did not run.");
                _failed = new InvalidOperationException(words);
                RunEnded(null, _failed);
                return;
            }
            _frame = said.Url;
            RunEnded(said.Url, null);
            _ = CheckAsync(widget, code);
        }
        catch (ApiException error)
        {
            _failed = error;
            RunEnded(null, error);
        }
        finally
        {
            _starting = false;
        }
    }

    /// <summary>Its errors, headless: the error panel in the Preview, its line linked to the Code.</summary>
    private async Task CheckAsync(WidgetFull widget, string code)
    {
        try
        {
            var checkedRun = await Widgets.CheckAsync(widget.Name, code);
            var found = checkedRun.Pages.SelectMany(p => p.Failed.Concat(p.Exceptions)).ToList();
            if (found.Count == 0 || !_running || _current != widget)
            {
                return;
            }
            var line = Regex.Match(string.Join('\n', found), @"\(line (\d+)\)");
            _failedLine = line.Success ? int.Parse(line.Groups[1].Value, System.Globalization.CultureInfo.InvariantCulture) : null;
            _failed = new InvalidOperationException(found[0]);
            RunEnded(null, _failed);
            await InvokeAsync(StateHasChanged);
        }
        catch (ApiException)
        {
            // the run shows what it drew
        }
    }

    /// <summary>Code (Esc): back to the code, and remembered for this widget.</summary>
    private async Task EditAsync()
    {
        if (_current is not null)
        {
            await Js.InvokeVoidAsync("sab.remember", $"widgets.view:{_current.Name}", "code");
        }
        await ToCodeAsync();
    }

    private async Task ToCodeAsync()
    {
        if (!_running)
        {
            return;
        }
        (_running, _frame, _failed) = (false, null, null);
        try
        {
            await Widgets.StopAsync(Window);
        }
        catch (ApiException)
        {
            // the run is gone already
        }
    }

    private async Task GoToLineAsync(int line)
    {
        await EditAsync();
        StateHasChanged();
        await Task.Yield();
        if (_editor is not null)
        {
            await _editor.RevealLineAsync(line);
        }
    }

    private Task EditorKeyAsync(EditorKey key) => key.Name switch
    {
        "runFile" => RunAsync(),
        "escape" => EditAsync(),
        _ => Task.CompletedTask,
    };

    private async Task NewAsync()
    {
        try
        {
            var made = await Widgets.NewAsync();
            await LoadListAsync();
            await SelectAsync(made.Name);
        }
        catch (ApiException error)
        {
            _listError = error;
        }
    }

    /// <summary>Copy as your own (a prebuilt one), or Copy to project / to library (the project's wins on its canvases).</summary>
    private async Task CopyAsync(string? to)
    {
        if (_current is null)
        {
            return;
        }
        try
        {
            var made = await Widgets.CopyAsync(_current.Name, to);
            await LoadListAsync();
            await SelectAsync(made.Name);
        }
        catch (ApiException error)
        {
            _listError = error;
        }
    }

    private async Task FoldAsync()
    {
        _listFolded = !_listFolded;
        await Js.InvokeVoidAsync("sab.remember", "widgets.folded", _listFolded ? "1" : "0");
    }

    private void ToggleProperties() => _propertiesOpen = !_propertiesOpen;

    /// <summary>The page's keys (canvas.js widgetKeys): Ctrl+B the list, Ctrl+Alt+B Properties, F5 Preview, Esc Code.</summary>
    [JSInvokable("Key")]
    public async Task KeyAsync(string key, bool alt)
    {
        switch (key)
        {
            case "b" when alt:
                ToggleProperties();
                break;
            case "b":
                await FoldAsync();
                break;
            case "F5":
                await RunAsync();
                break;
            case "Escape" when _running:
                await EditAsync();
                break;
            default:
                break;
        }
        StateHasChanged();
    }
}
