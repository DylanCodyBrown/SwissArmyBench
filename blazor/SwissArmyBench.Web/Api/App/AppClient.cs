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

    /// <summary>Everything in a window of its own (routes_pop_outs.py).</summary>
    public Task<PopOutsAnswer> PopOutsAsync() => _api.GetAsync<PopOutsAnswer>("/pop-outs");

    /// <summary>A page or a table popped out: this page opens its window itself (a click may open one).</summary>
    public Task<PopOutEntry> PopOutAsync(string key, string name, string address) =>
        _api.PostAsync<PopOutEntry>("/pop-outs", new { key, name, address, open = false });

    /// <summary>Back in its old place. front: the main window goes to it (the popped-out window's own Reattach);
    /// closed: the window that opened it saw it close (ignored when its window is there again).</summary>
    public Task ReattachAsync(string key, bool front, bool closed = false) => _api.PostAsync("/pop-outs/reattach", new { key, front, closed });

    /// <summary>A popped-out window's link out: true when a main window took it.</summary>
    public async Task<bool> FrontAsync(string address) =>
        (await _api.PostAsync<System.Text.Json.JsonElement>("/pop-outs/front", new { address })).GetProperty("shown").GetBoolean();

    public Task ShowPopOutAsync(string key) => _api.PostAsync("/pop-outs/show", new { key });
}
