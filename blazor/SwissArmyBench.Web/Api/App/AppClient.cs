namespace SwissArmyBench.Web.Api.App;

/// <summary>The app's own routes: its areas and modes (routes_modes.py), the rail and the front end
/// (routes_navigation.py).</summary>
public sealed class AppClient
{
    private readonly ApiClient _api;

    public AppClient(ApiClient api)
    {
        _api = api;
    }

    public async Task<IReadOnlyList<AreaInfo>> AreasAsync() => (await _api.GetAsync<AreasAnswer>("/app/areas")).Areas;

    public Task<ModeAnswer> ModeAsync() => _api.GetAsync<ModeAnswer>("/app/mode");

    /// <summary>An inline completion provider's status (its declared route).</summary>
    public Task<InlineStatus> InlineStatusAsync(string route) => _api.GetAsync<InlineStatus>(route);

    /// <summary>An inline completion provider turned on or off (its declared route).</summary>
    public Task InlineToggleAsync(string route, bool on) => _api.PostAsync(route, new { on });

    public Task<ModesAnswer> ModesAsync() => _api.GetAsync<ModesAnswer>("/app/modes");

    public Task<GatesAnswer> GatesAsync() => _api.GetAsync<GatesAnswer>("/app/gates");

    public Task<RailAnswer> RailAsync() => _api.GetAsync<RailAnswer>("/rail");

    public Task<RailAnswer> SetRailAsync(bool labels) => _api.PutAsync<RailAnswer>("/rail", new { labels });
}
