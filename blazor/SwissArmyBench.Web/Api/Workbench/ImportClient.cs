namespace SwissArmyBench.Web.Api.Workbench;

/// <summary>Bringing things into the open project (routes_project_scope.py): what a project folder or a loose file
/// offers, and the import of what is ticked (a document a name is taken for gets the next free one; a connection or
/// blade the library has is skipped, and said).</summary>
public sealed class ImportClient
{
    private readonly ApiClient _api;

    public ImportClient(ApiClient api)
    {
        _api = api;
    }

    public Task<ImportOffer> SourcesAsync(string from) => _api.PostAsync<ImportOffer>("/project/import/sources", new { from });

    /// <summary>The kind's ticked names imported (a loose file: itself).</summary>
    public Task<Imported> ImportAsync(string from, string kind, IReadOnlyList<string>? chosen) => chosen is null
        ? _api.PostAsync<Imported>("/project/import", new { from })
        : _api.PostAsync<Imported>("/project/import", new Dictionary<string, object> { ["from"] = from, [kind] = chosen });
}
