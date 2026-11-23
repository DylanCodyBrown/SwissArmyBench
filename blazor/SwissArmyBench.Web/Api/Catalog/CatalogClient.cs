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
}
