namespace SwissArmyBench.Web.Api.Connections;

/// <summary>How many queries run at once on a connection (routes_connection_slots.py): the slots, the limits, the
/// queries running, waiting and finished, a query's SQL, Cancel.</summary>
public sealed class QueriesClient
{
    private readonly ApiClient _api;

    public QueriesClient(ApiClient api)
    {
        _api = api;
    }

    public async Task<IReadOnlyList<SlotStatus>> SlotsAsync() => (await _api.GetAsync<SlotsAnswer>("/connections/slots")).Connections;

    public Task<SlotLimits> LimitsAsync(string name) => _api.GetAsync<SlotLimits>($"/connections/{ApiClient.Part(name)}/limits");

    public Task<SlotLimits> SaveLimitsAsync(string name, SlotLimits limits) =>
        _api.PutAsync<SlotLimits>($"/connections/{ApiClient.Part(name)}/limits", new { total = limits.Total, agent = limits.Agent, wait = limits.Wait });

    public Task<QueriesListing> QueriesAsync() => _api.GetAsync<QueriesListing>("/connections/queries");

    public Task<QuerySql> SqlAsync(string id) => _api.GetAsync<QuerySql>($"/connections/queries/{ApiClient.Part(id)}/sql");

    public Task CancelAsync(string id) => _api.PostAsync($"/connections/queries/{ApiClient.Part(id)}/cancel", new { });

    public Task ClearAsync() => _api.PostAsync("/connections/queries/clear", new { });

    /// <summary>A window sent somewhere (a new query on a connection: "query:Shop"; "grids").</summary>
    public Task NavigateAsync(string to) => _api.PostAsync("/navigate", new { to });
}
