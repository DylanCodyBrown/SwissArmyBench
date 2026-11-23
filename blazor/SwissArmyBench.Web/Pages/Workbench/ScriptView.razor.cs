using Microsoft.AspNetCore.Components;

using SwissArmyBench.Web.Api;
using SwissArmyBench.Web.Api.Workbench;
using SwissArmyBench.Web.Components;
using SwissArmyBench.Web.State;

namespace SwissArmyBench.Web.Pages.Workbench;

public partial class ScriptView
{
    private CellModel _console = new();
    private CodeEditor? _editor;
    private CellRunner? _runner;
    private string _line = string.Empty;
    private Exception? _error;

    [Inject]
    private WorkbenchClient Workbench { get; set; } = default!;

    [Inject]
    private PythonSession Session { get; set; } = default!;

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

    private void Clear()
    {
        _console.Outputs.Clear();
        _console.ErrorDetail = null;
    }

    private Task AnswerAsync(string line) => _runner?.AnswerAsync(_console, line) ?? Task.CompletedTask;
}
