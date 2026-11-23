namespace SwissArmyBench.Web.Api.Workbench;

/// <summary>
/// What the Notebooks and Scripts pages export (routes_projects.py, routes_workbench.py, routes_sab_projects.py,
/// routes_project_outline.py): data.py from data.ipynb, a document as one self-contained automation, the project
/// copied to another folder, and its outline.
/// </summary>
public sealed class ExportsClient
{
    private readonly ApiClient _api;

    public ExportsClient(ApiClient api)
    {
        _api = api;
    }

    public Task<DataExport> ExportDataAsync(string folder) => _api.PostAsync<DataExport>("/projects/export-data", new { folder });

    /// <summary>A document exported: check (only look: a connection that runs only here), stub (export the rest with a
    /// FILL IN stub for what cannot go).</summary>
    public Task<ScriptExport> ExportScriptAsync(IReadOnlyDictionary<string, object?> body, bool check = false, bool stub = false) =>
        _api.PostAsync<ScriptExport>("/workbench/export-script", new Dictionary<string, object?>(body) { ["check"] = check, ["stub"] = stub });

    public Task<ProjectCopy> CopyProjectAsync(string path, bool data) => _api.PostAsync<ProjectCopy>("/project/copy", new { path, data });

    public Task<ProjectOutline> OutlineAsync() => _api.PostAsync<ProjectOutline>("/project/outline", new { });
}
