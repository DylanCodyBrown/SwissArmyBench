namespace SwissArmyBench.Web.Api.Sharing;

/// <summary>Share… a running app with your organization (routes_sharing.py, Microsoft Dev Tunnels): the state for
/// an app, devtunnel's install, the sign-in (in the browser or with a code), start and stop.</summary>
public sealed class SharingClient
{
    private readonly ApiClient _api;

    public SharingClient(ApiClient api)
    {
        _api = api;
    }

    /// <summary>The state for one app (fresh: devtunnel asked again, while signing in).</summary>
    public Task<SharingStatus> StatusAsync(string kind, string app, bool fresh = false) =>
        _api.GetAsync<SharingStatus>($"/sharing?kind={ApiClient.Part(kind)}&app={ApiClient.Part(app)}{(fresh ? "&fresh=1" : string.Empty)}");

    public Task InstallAsync() => _api.PostAsync("/sharing/install");

    public Task SignInAsync(bool device) => _api.PostAsync("/sharing/sign-in", new { device });

    public Task StartAsync(string kind, string app) => _api.PostAsync("/sharing/start", new { kind, app });

    public Task StopAsync(string kind, string app) => _api.PostAsync("/sharing/stop", new { kind, app });
}
