using Microsoft.AspNetCore.Components;

using SwissArmyBench.Web.Api;
using SwissArmyBench.Web.Api.Workbench;
using SwissArmyBench.Web.Components;

namespace SwissArmyBench.Web.Pages.Workbench;

public partial class SqlFileView
{
    private CodeEditor? _editor;
    private SqlRun? _built;
    private SqlFailure? _failed;
    private bool _running;
    private CancellationTokenSource? _cancel;

    [Inject]
    private ScriptIdeClient Ide { get; set; } = default!;

    [Parameter, EditorRequired]
    public string Text { get; set; } = string.Empty;

    /// <summary>Where it is saved (null until Save as): its name is the table's.</summary>
    [Parameter]
    public string? Path { get; set; }

    /// <summary>An untitled file's table name ("query" until it is saved with a name).</summary>
    [Parameter]
    public string? Table { get; set; }

    [Parameter]
    public EventCallback<string> OnTextChanged { get; set; }

    [Parameter]
    public EventCallback<string> OnPageKey { get; set; }

    [Parameter]
    public EventCallback<int> OnProblems { get; set; }

    /// <summary>A run built its table: the page brings the Tables page forward on it.</summary>
    [Parameter]
    public EventCallback<SqlRun> OnBuilt { get; set; }

    /// <summary>Open in Tables: the table's tab on the Tables page.</summary>
    [Parameter]
    public EventCallback<SqlRun> OnOpenTable { get; set; }

    public CodeEditor? Editor => _editor;

    public bool Running => _running;

    /// <summary>Where the file runs as its header says (null: the open tables, DuckDB).</summary>
    public string? Connection => SqlHeader.Of(Text);

    private string Status => _running ? "Running…"
        : _built is { } built ? $"{Rows(built.Rows)} in {built.Table}{(built.Connection is { } on ? $", from {on}" : string.Empty)}."
        : _failed is not null ? "Failed." : string.Empty;

    public static string Rows(long rows) => $"{rows:N0} {(rows == 1 ? "row" : "rows")}";

    private IntelContext IntelFor() => new(null, Path, null, false, [], [], Path ?? "untitled.sql", Connection);

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

    /// <summary>Run file (F5): the file's one query.</summary>
    public Task RunFileAsync() => RunAsync(null, null);

    /// <summary>Run selection (Ctrl+Enter): the selected text, else the statement under the cursor.</summary>
    public async Task RunSelectionAsync()
    {
        var (selected, line) = _editor is null ? (string.Empty, 1) : await _editor.SelectedAsync();
        await RunAsync(line, selected.Length > 0 ? selected : null);
    }

    public void Cancel() => _cancel?.Cancel();

    private async Task RunAsync(int? line, string? selection)
    {
        if (_running)
        {
            return;
        }
        var text = _editor is null ? Text : await _editor.TextAsync();
        await OnTextChanged.InvokeAsync(text);
        (_running, _failed) = (true, null);
        _cancel = new CancellationTokenSource();
        StateHasChanged();
        await MarkAsync(null, null);
        try
        {
            var request = new SqlRunRequest(Path, text, SqlHeader.Of(text) ?? string.Empty, line, selection, Path is null ? Table : null);
            _built = await Ide.RunSqlAsync(request, _cancel.Token);
            await OnBuilt.InvokeAsync(_built);
        }
        catch (OperationCanceledException)
        {
            _built = null;
            _failed = new SqlFailure("Cancelled.", null, null);
        }
        catch (ApiException error)
        {
            _built = null;
            _failed = SqlFailure.Of(error);
            await MarkAsync(_failed.Line, _failed.Words);
        }
        _running = false;
    }

    private Task MarkAsync(int? line, string? words) => _editor?.MarkErrorAsync(line, words) ?? Task.CompletedTask;

    private async Task ClearAsync()
    {
        (_built, _failed) = (null, null);
        await MarkAsync(null, null);
    }

    public Task RevealLineAsync(int line) => _editor?.RevealLineAsync(line) ?? Task.CompletedTask;

    public Task InsertAsync(string text) => _editor?.InsertAsync(text) ?? Task.CompletedTask;
}
