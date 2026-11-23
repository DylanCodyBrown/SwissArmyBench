namespace SwissArmyBench.Web.Api.Blades;

/// <summary>The loaded catalogs (routes_catalogs.py, routes_connections.py): the list, a catalog's schemas, tables
/// and columns, a search, removing one; a table's first rows and its grid on its connection; a Power BI dataset's
/// relationships imported.</summary>
public sealed class CatalogClient
{
    private readonly ApiClient _api;

    public CatalogClient(ApiClient api)
    {
        _api = api;
    }

    private static string At(string name) => $"/catalogs/{ApiClient.Part(name)}";

    private static string Query(params (string Key, string? Value)[] pairs) =>
        "?" + string.Join('&', pairs.Where(p => !string.IsNullOrEmpty(p.Value)).Select(p => $"{p.Key}={Uri.EscapeDataString(p.Value!)}"));

    public Task<CatalogList> ListAsync() => _api.GetAsync<CatalogList>("/catalogs");

    public Task<CatalogSchemas> SchemasAsync(string name) => _api.GetAsync<CatalogSchemas>($"{At(name)}/schemas");

    public Task<CatalogTables> TablesAsync(string name, string schema, string? database) =>
        _api.GetAsync<CatalogTables>($"{At(name)}/tables{Query(("schema", schema), ("database", database), ("limit", "500"))}");

    public Task<CatalogColumns> ColumnsAsync(string name, CatalogTable table) =>
        _api.GetAsync<CatalogColumns>($"{At(name)}/columns{Query(("schema", table.Schema), ("table", table.Table), ("database", table.Database))}");

    public Task<CatalogSearch> SearchAsync(string name, string text) => _api.GetAsync<CatalogSearch>($"{At(name)}/search{Query(("q", text), ("limit", "50"))}");

    public Task RemoveAsync(string name) => _api.DeleteAsync(At(name));

    public Task<CatalogPreview> PreviewAsync(string name, CatalogTable table) =>
        _api.PostAsync<CatalogPreview>($"/connections/{ApiClient.Part(name)}/preview", new { schema = table.Schema, table = table.Table, database = NullIfEmpty(table.Database) });

    public Task<CatalogOpened> OpenAsync(string name, CatalogTable table) =>
        _api.PostAsync<CatalogOpened>($"/connections/{ApiClient.Part(name)}/open", new { schema = table.Schema, table = table.Table, database = NullIfEmpty(table.Database) });

    public Task ImportRelationshipsAsync(string name, string dataset) =>
        _api.PostAsync($"/connections/{ApiClient.Part(name)}/relationships", new { dataset });

    private static string? NullIfEmpty(string text) => text.Length == 0 ? null : text;
}
