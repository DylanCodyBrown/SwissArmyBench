using Microsoft.AspNetCore.Components;

using SwissArmyBench.Web.Api;
using SwissArmyBench.Web.Api.Workbench;
using SwissArmyBench.Web.Components;

namespace SwissArmyBench.Web.Pages.Workbench;

public partial class PowerQueryFileView
{
    private CodeEditor? _editor;
    private PowerQueryRun? _built;
    private PowerQuerySqlAnswer? _sql;
    private SqlFailure? _failed;
    private bool _running;
    private CancellationTokenSource? _cancel;

    [Inject]
    private ScriptIdeClient Ide { get; set; } = default!;

    [Parameter, EditorRequired]
    public string Text { get; set; } = string.Empty;

    /// <summary>Where it is saved: a plain let ... in file's one query is named after it.</summary>
    [Parameter]
    public string? Path { get; set; }

    [Parameter]
    public EventCallback<string> OnTextChanged { get; set; }

    [Parameter]
    public EventCallback<string> OnPageKey { get; set; }

    [Parameter]
    public EventCallback<int> OnProblems { get; set; }

    /// <summary>A run built its tables: the page brings the Tables page forward on the last one.</summary>
    [Parameter]
    public EventCallback<PowerQueryRun> OnBuilt { get; set; }

    /// <summary>Open in Tables: one built table's tab on the Tables page.</summary>
    [Parameter]
    public EventCallback<PowerQueryTable> OnOpenTable { get; set; }

    public CodeEditor? Editor => _editor;

    public bool Running => _running;

    private string Status => _running ? "Running…"
        : _failed is not null ? "Failed."
        : _built is { } built ? $"{Tables(built.Tables.Count)} built from {(built.Tables.Count == 1 ? "its" : "their")} original sources."
        : _sql is { } composed ? $"What runs in DuckDB for {Tables(composed.Queries.Count)}."
        : string.Empty;

    /// <summary>Whether a path is a Power Query file's (.pq or .m).</summary>
    public static bool IsFile(string? path) => path is not null
        && (path.EndsWith(".pq", StringComparison.OrdinalIgnoreCase) || path.EndsWith(".m", StringComparison.OrdinalIgnoreCase));

    public static string Tables(int count) => $"{count:N0} {(count == 1 ? "table" : "tables")}";

    // The editor's lint asks the server with this file's path (a plain file's query is named after it).
    private IntelContext IntelFor() => new(null, Path, null, false, [], [], Path ?? "query.pq", null);

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
                await RunQueryAsync();
                break;
            default:
                break;
        }
    }

    /// <summary>Run file (F5): every query of the file that is a table.</summary>
    public Task RunFileAsync() => RunAsync(null);

    /// <summary>Run query (Ctrl+Enter): the query under the cursor.</summary>
    public async Task RunQueryAsync() => await RunAsync(await CursorLineAsync());

    /// <summary>Show as SQL: the DuckDB SQL composed for the query under the cursor.</summary>
    public async Task ShowSqlAsync()
    {
        var line = await CursorLineAsync();
        await AskAsync(async (request, cancel) =>
        {
            _sql = await Ide.PowerQuerySqlAsync(request with { Line = line }, cancel);
            _built = null;
        });
    }

    public void Cancel() => _cancel?.Cancel();

    private async Task<int> CursorLineAsync() => _editor is null ? 1 : Math.Max(1, await _editor.CursorLineAsync());

    private Task RunAsync(int? line) => AskAsync(async (request, cancel) =>
    {
        _built = await Ide.RunPowerQueryAsync(request with { Line = line }, cancel);
        _sql = null;
        await OnBuilt.InvokeAsync(_built);
    });

    private async Task AskAsync(Func<PowerQueryRequest, CancellationToken, Task> ask)
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
            await ask(new PowerQueryRequest(Path, text), _cancel.Token);
        }
        catch (OperationCanceledException)
        {
            (_built, _sql) = (null, null);
            _failed = new SqlFailure("Cancelled.", null, null);
        }
        catch (ApiException error)
        {
            (_built, _sql) = (null, null);
            _failed = SqlFailure.Of(error);
            await MarkAsync(_failed.Line, _failed.Words);
        }
        _running = false;
        StateHasChanged(); // asked from the bar or a key: the Output draws what came back
    }

    private Task MarkAsync(int? line, string? words) => _editor?.MarkErrorAsync(line, words) ?? Task.CompletedTask;

    private async Task ClearAsync()
    {
        (_built, _sql, _failed) = (null, null, null);
        await MarkAsync(null, null);
    }

    public Task RevealLineAsync(int line) => _editor?.RevealLineAsync(line) ?? Task.CompletedTask;

    public Task InsertAsync(string text) => _editor?.InsertAsync(text) ?? Task.CompletedTask;
}
