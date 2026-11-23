namespace SwissArmyBench.Web.Api.Settings;

/// <summary>What Settings reads and sets: the team (routes_team.py), updates (routes_updates.py), beta mode
/// (routes_beta_log.py), Claude (routes_claude.py) and the project type's gates (routes_modes.py).</summary>
public sealed class SettingsClient
{
    private readonly ApiClient _api;

    public SettingsClient(ApiClient api)
    {
        _api = api;
    }

    public Task<TeamStatus> TeamAsync() => _api.GetAsync<TeamStatus>("/team");

    public Task TeamPullAsync() => _api.PostAsync("/team/pull");

    public Task TeamPushAsync() => _api.PostAsync("/team/push");

    public Task TeamShowAsync() => _api.PostAsync("/team/show");

    public Task<UpdatesStatus> UpdatesAsync() => _api.GetAsync<UpdatesStatus>("/updates");

    /// <summary>Update to X: the app stops, installs and starts again (the server asks when work would be lost).</summary>
    public Task UpdateAsync(string version) => _api.PostAsync("/updates/install", new { version });

    public Task<BetaStatus> BetaAsync() => _api.GetAsync<BetaStatus>("/beta");

    public Task<BetaStatus> SetBetaAsync(bool on) => _api.PutAsync<BetaStatus>("/beta", new { on });

    public Task ClearBetaLogAsync() => _api.DeleteAsync("/beta/log");

    public Task ExportBetaLogAsync(string path) => _api.PostAsync("/beta/export", new { path });

    public Task BetaNoteAsync(string text) => _api.PostAsync("/beta/notes", new { text });

    public Task<ClaudeStatus> ClaudeAsync() => _api.GetAsync<ClaudeStatus>("/claude");

    public Task<ClaudeStatus> SetClaudeBypassAsync(bool bypass) => _api.PutAsync<ClaudeStatus>("/claude", new { bypass });

    public Task SetEveryFeatureAsync(bool every) => _api.PostAsync("/app/gates", new { every });
}
