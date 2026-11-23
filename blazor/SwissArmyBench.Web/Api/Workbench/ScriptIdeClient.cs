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
}
