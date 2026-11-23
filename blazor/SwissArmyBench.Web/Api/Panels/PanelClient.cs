namespace SwissArmyBench.Web.Api.Panels;

/// <summary>An extension's own panel at the route its backend names (GET /app/areas' panel, GET /extensions' panel):
/// read, and each change posted (a switch, an action, a choice), the panel as it is after.</summary>
public sealed class PanelClient
{
    private readonly ApiClient _api;

    public PanelClient(ApiClient api)
    {
        _api = api;
    }

    public Task<PanelData> ReadAsync(string route) => _api.GetAsync<PanelData>(route);

    public Task<PanelData> PostAsync(string route, IReadOnlyDictionary<string, object?> body) => _api.PostAsync<PanelData>(route, body);
}
