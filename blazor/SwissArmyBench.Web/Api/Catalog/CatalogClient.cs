namespace SwissArmyBench.Web.Api.Catalog;

/// <summary>The Catalog page's search (routes_explorer.py): one search over every connection's tables, the open
/// tables, structures, APIs, variables and blades.</summary>
public sealed class CatalogClient
{
    private readonly ApiClient _api;

    public CatalogClient(ApiClient api)
    {
        _api = api;
    }

    public Task<SearchAnswer> SearchAsync(string text) => _api.GetAsync<SearchAnswer>($"/explorer/search?q={ApiClient.Part(text)}");

    /// <summary>The search narrowed: the kinds shown, one connection's results, the tables with a column.</summary>
    public Task<SearchAnswer> SearchAsync(string text, IReadOnlyCollection<string> kinds, string connection, string column, int? limit = null)
    {
        var parts = new List<string>();
        if (text.Trim().Length > 0)
        {
            parts.Add($"q={ApiClient.Part(text.Trim())}");
        }
        if (kinds.Count > 0)
        {
            parts.Add($"kinds={ApiClient.Part(string.Join(',', kinds))}");
        }
        if (connection.Length > 0)
        {
            parts.Add($"connection={ApiClient.Part(connection)}");
        }
        if (column.Length > 0)
        {
            parts.Add($"column={ApiClient.Part(column)}");
        }
        if (limit is { } most)
        {
            parts.Add($"limit={most}");
        }
        return _api.GetAsync<SearchAnswer>($"/explorer/search?{string.Join('&', parts)}");
    }

    /// <summary>The tree with nothing typed: every connection's tables and the sections, narrowed by kind and
    /// connection, the sandbox's tables in the order asked (name, rows, source, created, changed).</summary>
    public Task<BrowseAnswer> BrowseAsync(IReadOnlyCollection<string> kinds, string connection, string sort = "name", string order = "asc")
    {
        var parts = new List<string> { $"sort={ApiClient.Part(sort)}", $"order={ApiClient.Part(order)}" };
        if (kinds.Count > 0)
        {
            parts.Add($"kinds={ApiClient.Part(string.Join(',', kinds))}");
        }
        if (connection.Length > 0)
        {
            parts.Add($"connection={ApiClient.Part(connection)}");
        }
        return _api.GetAsync<BrowseAnswer>($"/explorer/browse?{string.Join('&', parts)}");
    }

    /// <summary>A connection's table for the detail side: its columns, SQL name and code.</summary>
    public Task<TableDetail> TableAsync(string connection, TablePlace place) =>
        _api.GetAsync<TableDetail>($"/explorer/table?connection={ApiClient.Part(connection)}&database={ApiClient.Part(place.Database ?? string.Empty)}&schema={ApiClient.Part(place.Schema ?? string.Empty)}&table={ApiClient.Part(place.Table)}");

    /// <summary>A connection's (a dataset's, a schema's) relationships into the model.</summary>
    public Task<ImportedRelationships> ImportRelationshipsAsync(string connection, string dataset) =>
        _api.PostAsync<ImportedRelationships>($"/connections/{ApiClient.Part(connection)}/relationships", dataset.Length > 0 ? new { dataset } : (object)new { });

    /// <summary>A connection's catalog loaded in the background (its notice draws the search again).</summary>
    public Task LoadCatalogAsync(string connection) => _api.PostAsync($"/connections/{ApiClient.Part(connection)}/catalog");
}
