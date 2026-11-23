using Microsoft.AspNetCore.Components;
using Microsoft.JSInterop;

using SwissArmyBench.Web.Api;
using SwissArmyBench.Web.Api.Workbench;
using SwissArmyBench.Web.Components;
using SwissArmyBench.Web.State;

namespace SwissArmyBench.Web.Pages.Workbench;

public partial class ScriptView
{
    private CellModel _console = new();
    private CodeEditor? _editor;
    private DebugPanel? _debug;
    private CellRunner? _runner;
    private string _line = string.Empty;
    private Exception? _error;

    [Inject]
    private WorkbenchClient Workbench { get; set; } = default!;

    [Inject]
    private PythonSession Session { get; set; } = default!;

    [Inject]
    private IJSRuntime Js { get; set; } = default!;

    [Parameter, EditorRequired]
    public string Text { get; set; } = string.Empty;

    /// <summary>Where it is saved (null until Save as).</summary>
    [Parameter]
    public string? Path { get; set; }

    /// <summary>The text on disk is the text on screen (Run file runs the saved file; else the text as it is).</summary>
    [Parameter]
    public bool Saved { get; set; }

    /// <summary>The console's runs, kept with its document (a tab moved keeps them).</summary>
    [Parameter]
    public CellModel? Console { get; set; }

    [Parameter]
    public EventCallback<string> OnTextChanged { get; set; }

    [Parameter]
    public EventCallback<string> OnPageKey { get; set; }

    /// <summary>The ghost text providers the mode declares.</summary>
    [Parameter]
    public IReadOnlyList<SwissArmyBench.Web.Api.App.InlineProvider> Inline { get; set; } = [];

    private object InlineDocument() => new { key = Path ?? "untitled", name = System.IO.Path.GetFileName(Path ?? "untitled.py"), kind = "script", language = "python", text = Text };

    /// <summary>The IDE moves at the cursor (F12, Shift+F12, F2, Shift+Alt+F), for the page.</summary>
    [Parameter]
    public EventCallback<IdeMove> OnIde { get; set; }

    /// <summary>Start debugging (Ctrl+Shift+D): the script as it is on screen, under the debugger.</summary>
    public async Task DebugAsync()
    {
        if (_debug is not null && _editor is not null)
        {
            await _debug.StartAsync(await _editor.TextAsync());
        }
    }

    /// <summary>The debugger's moves for the palette: toggle at the cursor, the steps, stop.</summary>
    public DebugPanel? Debugger => _debug;

    private Task GutterAsync(GutterClick click) => _debug?.GutterAsync(click) ?? Task.CompletedTask;

    /// <summary>The cursor to a line, with the focus (a definition, a reference, a search result).</summary>
    public Task RevealLineAsync(int line) => _editor?.RevealLineAsync(line) ?? Task.CompletedTask;

    /// <summary>The lint's problems at warning or worse, as they change (the status bar's count).</summary>
    [Parameter]
    public EventCallback<int> OnProblems { get; set; }


    protected override void OnInitialized()
    {
        _runner = new CellRunner(Workbench, Session);
        _console = Console ?? new CellModel();
    }

    /// <summary>A blade's line put in at the cursor.</summary>
    public Task InsertAsync(string text) => _editor?.InsertAsync(text) ?? Task.CompletedTask;

    private IntelContext IntelFor() => new(Session.Kernel, Path, Session.Python, false, [], [], Path ?? "untitled.py", null);

    private Task TextChangedAsync(string text) => OnTextChanged.InvokeAsync(text);

    private async Task KeyAsync(EditorKey key)
    {
        await OnTextChanged.InvokeAsync(key.Text);
        switch (key.Name)
        {
            case "save" or "saveAs":
                await OnPageKey.InvokeAsync(key.Name);
                break;
            case "toggleBreakpoint" when _debug is not null:
                await _debug.ToggleAtCursorAsync();
                break;
            case "stepOver" when _debug is not null:
                await _debug.StepAsync("over");
                break;
            case "stepOut" when _debug is not null:
                await _debug.StepAsync("out");
                break;
            case "stopDebugging" when _debug is not null:
                await _debug.StopAsync();
                break;
            case "runFile" when _debug?.Paused == true:
                await _debug.StepAsync("continue"); // paused: F5 continues
                break;
            case "runFile":
                await RunFileAsync();
                break;
            case "runHere" or "run":
                await RunSelectionAsync();
                break;
            default:
                break;
        }
    }

    /// <summary>The script as `python script.py` runs it (its own __main__ and __file__): the saved file when it
    /// is saved, else the text on screen.</summary>
    public async Task RunFileAsync()
    {
        // The editor's text as it is now: typing not yet told to the page runs too.
        var text = _editor is null ? Text : await _editor.TextAsync();
        var request = Saved && Path is not null && text == Text
            ? new RunRequest(string.Empty, "file", Path: Path, Document: Path)
            : new RunRequest(text, "file", Document: Path);
        await RunAsync(request);
    }

    /// <summary>Run statement: the selected lines, else the cursor's line (Ctrl+Enter).</summary>
    public async Task RunSelectionAsync()
    {
        if (_editor is not null)
        {
            await RunAsync(new RunRequest(await _editor.SelectionAsync(), Document: Path));
        }
    }

    private async Task RunLineAsync()
    {
        var line = _line;
        _line = string.Empty;
        if (line.Trim().Length > 0)
        {
            await RunAsync(new RunRequest(line, Document: Path));
        }
    }

    private async Task RunAsync(RunRequest request)
    {
        if (_runner is null)
        {
            return;
        }
        try
        {
            await _runner.RunAsync(_console, request, Path, () => InvokeAsync(StateHasChanged));
            _error = null;
        }
        catch (ApiException error)
        {
            _error = error;
        }
    }

    /// <summary>Clear the console (the palette's).</summary>
    public void ClearConsole() => Clear();

    /// <summary>The console's line takes the focus (Go to the console).</summary>
    public Task FocusConsoleAsync() => Js.InvokeVoidAsync("sab.focus", ".wb-console-line input").AsTask();

    /// <summary>Run code in the console, as if typed there.</summary>
    public Task RunInConsoleAsync(string code) => RunAsync(new RunRequest(code, Document: Path));

    /// <summary>What the console shows, as text.</summary>
    public string ConsoleText => string.Join('\n', _console.Outputs.Select(o => OutputReader.Plain(OutputReader.Text(o, "text"))));

    /// <summary>The code's size (the palette's Code size): 13 px is 100%.</summary>
    public Task SetCodeSizeAsync(int px) => _editor?.SetFontSizeAsync(px) ?? Task.CompletedTask;

    private void Clear()
    {
        _console.Outputs.Clear();
        _console.ErrorDetail = null;
    }

    /// <summary>An error's frame in this script: its line shown.</summary>
    private Task GoToAsync(RunErrorFrame frame) =>
        frame.Where is "cell" or "file" && _editor is not null ? _editor.RevealLineAsync(frame.Line) : Task.CompletedTask;

    /// <summary>An error panel's fix on the script's text: a text replaced, an import line added at the top.</summary>
    private Task FixAsync(RunErrorFix fix)
    {
        var text = fix switch
        {
            { Kind: "replace", Target: { } target, Text: { } by } when Text.Contains(target, StringComparison.Ordinal) =>
                string.Concat(Text.AsSpan(0, Text.IndexOf(target, StringComparison.Ordinal)), by, Text.AsSpan(Text.IndexOf(target, StringComparison.Ordinal) + target.Length)),
            { Kind: "import", Line: { } line } => $"{line}\n{Text}",
            _ => null,
        };
        return text is null ? Task.CompletedTask : OnTextChanged.InvokeAsync(text);
    }

    private Task AnswerAsync(string line) => _runner?.AnswerAsync(_console, line) ?? Task.CompletedTask;
}
