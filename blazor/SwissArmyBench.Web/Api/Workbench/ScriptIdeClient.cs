namespace SwissArmyBench.Web.Api.Workbench;

/// <summary>
/// The Scripts page's IDE moves (routes_script_ide.py, the editors' one Jedi world): go to definition, find all
/// references, rename across the project's modules (its plan, then applied), Ruff's format, and search and replace
/// across the project's scripts.
/// </summary>
public sealed class ScriptIdeClient
{
    private readonly ApiClient _api;

    public ScriptIdeClient(ApiClient api)
    {
        _api = api;
    }

    public Task<IdeDefinitions> DefinitionAsync(string text, int line, int column, string? path) =>
        _api.PostAsync<IdeDefinitions>("/scripts/definition", new { text, line, column, path });

    public Task<IdeReferences> ReferencesAsync(string text, int line, int column, string? path) =>
        _api.PostAsync<IdeReferences>("/scripts/references", new { text, line, column, path });

    public Task<IdePlan> RenamePlanAsync(string text, int line, int column, string? path, string to) =>
        _api.PostAsync<IdePlan>("/scripts/rename", new { text, line, column, path, to });

    /// <summary>The rename applied to the other files; the open document's own change stays unsaved in its editor.</summary>
    public Task<IdeWritten> RenameAsync(string text, int line, int column, string? path, string to) =>
        _api.PostAsync<IdeWritten>("/scripts/rename", new { text, line, column, path, to, apply = true, unsaved = true });

    public Task<IdeFormatted> FormatAsync(string text, string? python) => _api.PostAsync<IdeFormatted>("/scripts/format", new { text, python });

    public Task<IdeSearch> SearchAsync(string query, bool regex, bool matchCase, bool word) =>
        _api.PostAsync<IdeSearch>("/scripts/search", new { query, regex, @case = matchCase, word });

    public Task<IdePlan> ReplacePlanAsync(string query, bool regex, bool matchCase, bool word, string to) =>
        _api.PostAsync<IdePlan>("/scripts/replace", new { query, regex, @case = matchCase, word, to });

    public Task<IdeWritten> ReplaceAsync(string query, bool regex, bool matchCase, bool word, string to) =>
        _api.PostAsync<IdeWritten>("/scripts/replace", new { query, regex, @case = matchCase, word, to, apply = true });

    public Task<FileMove> MovePlanAsync(string path, string to) => _api.PostAsync<FileMove>("/scripts/files/move", new { path, to });

    public Task<FileMove> MoveAsync(string path, string to) => _api.PostAsync<FileMove>("/scripts/files/move", new { path, to, apply = true });

    public Task<FilePlace> DuplicateAsync(string path) => _api.PostAsync<FilePlace>("/scripts/files/duplicate", new { path });

    /// <summary>To the system's trash (the user's own).</summary>
    public Task<FilePlace> DeleteAsync(string path) => _api.PostAsync<FilePlace>("/scripts/files/delete", new { path });

    public Task<FilePlace> NewPackageAsync(string name, string? parent) => _api.PostAsync<FilePlace>("/scripts/files/package", new { name, parent });

    /// <summary>New file's types and the open project's folders.</summary>
    public Task<NewFileOptions> NewFileOptionsAsync() => _api.GetAsync<NewFileOptions>("/scripts/files/new");

    /// <summary>Where a new file would go, or the one sentence why not (a taken name, a wrong ending): nothing written.</summary>
    public Task<NewFileMade> CheckNewFileAsync(NewFileRequest request, CancellationToken cancel = default) =>
        _api.PostAsync<NewFileMade>("/scripts/files/new", new { type = request.Type, name = request.Name, folder = request.Folder, connection = request.Connection, variant = request.Variant, source = request.Source, check = true }, cancel);

    /// <summary>A new file, named and written with its type's starter (in the open project, else the folder named).</summary>
    public Task<NewFileMade> NewFileAsync(NewFileRequest request) =>
        _api.PostAsync<NewFileMade>("/scripts/files/new", new { type = request.Type, name = request.Name, folder = request.Folder, connection = request.Connection, variant = request.Variant, source = request.Source });

    /// <summary>A .sql file run: its text as on screen, where it runs ("" the open tables), and with a line, Run
    /// selection there (the selected text, else the statement at the line).</summary>
    public Task<SqlRun> RunSqlAsync(SqlRunRequest request, CancellationToken cancel = default) =>
        _api.PostAsync<SqlRun>("/scripts/sql/run", new
        {
            path = request.Path,
            text = request.Text,
            connection = request.Connection,
            line = request.Line,
            selection = request.Selection,
            table = request.Table,
        }, cancel);

    /// <summary>A Power Query file run: every query that is a table (with a line: the one there), each the open
    /// table of its name, read from its original sources.</summary>
    public Task<PowerQueryRun> RunPowerQueryAsync(PowerQueryRequest request, CancellationToken cancel = default) =>
        _api.PostAsync<PowerQueryRun>("/scripts/pq/run", PowerQueryBody(request), cancel);

    /// <summary>Show as SQL: the DuckDB SQL composed for each query (with a line: the one there). Nothing is built.</summary>
    public Task<PowerQuerySqlAnswer> PowerQuerySqlAsync(PowerQueryRequest request, CancellationToken cancel = default) =>
        _api.PostAsync<PowerQuerySqlAnswer>("/scripts/pq/sql", PowerQueryBody(request), cancel);

    /// <summary>Export to run anywhere: the saved file with duckpq.py and run.py beside it, in a folder of its own.</summary>
    public Task<PowerQueryExport> ExportPowerQueryAsync(string path) => _api.PostAsync<PowerQueryExport>("/scripts/pq/export", new { path });

    /// <summary>What a linked Power Query file's tab shows: its workbook, and what stands in a save's way.</summary>
    public Task<WorkbookLink> WorkbookLinkAsync(string path, string text, CancellationToken cancel = default) =>
        _api.PostAsync<WorkbookLink>("/scripts/pq/workbook", new { path, text }, cancel);

    /// <summary>A save's dry run: each workbook query changed, added, kept or the same. Nothing is written.</summary>
    public Task<WorkbookSave> PreviewWorkbookSaveAsync(string path, string text, CancellationToken cancel = default) =>
        _api.PostAsync<WorkbookSave>("/scripts/pq/workbook/preview", new { path, text }, cancel);

    /// <summary>The saved file's queries written into its workbook's Data Mashup, and nothing else of it
    /// (<paramref name="force"/>: Keep mine, over queries changed on disk).</summary>
    public Task<WorkbookSave> SaveIntoWorkbookAsync(string path, bool force = false, bool add = false, CancellationToken cancel = default) =>
        _api.PostAsync<WorkbookSave>("/scripts/pq/workbook/save", new { path, force, add }, cancel);

    /// <summary>Reload: the workbook's queries read again into the linked file.</summary>
    public Task<WorkbookReload> ReloadWorkbookAsync(string path, CancellationToken cancel = default) =>
        _api.PostAsync<WorkbookReload>("/scripts/pq/workbook/reload", new { path }, cancel);

    private static object PowerQueryBody(PowerQueryRequest request) =>
        new { path = request.Path, text = request.Text, line = request.Line, query = request.Query };

    /// <summary>Edit in Scripts: a table a query made, as its file (a .sql file made now when it is not there yet; a
    /// Power Query's table: the .pq file it ran from).</summary>
    public Task<SqlTableFile> SqlForTableAsync(string table) => _api.PostAsync<SqlTableFile>("/scripts/sql/for-table", new { table });
}
