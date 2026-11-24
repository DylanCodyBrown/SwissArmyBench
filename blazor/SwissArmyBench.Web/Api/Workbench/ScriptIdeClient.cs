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

    /// <summary>Edit in Scripts: a table a query made, as its .sql file (made now when it is not there yet).</summary>
    public Task<SqlTableFile> SqlForTableAsync(string table) => _api.PostAsync<SqlTableFile>("/scripts/sql/for-table", new { table });
}
