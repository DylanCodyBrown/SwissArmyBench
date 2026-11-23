using System.Text.Json;

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

    public Task<JsonElement> TeamPullAsync() => _api.PostAsync<JsonElement>("/team/pull");

    public Task<JsonElement> TeamPushAsync() => _api.PostAsync<JsonElement>("/team/push");

    public Task<JsonElement> TeamShowAsync() => _api.PostAsync<JsonElement>("/team/show");

    public Task<UpdatesStatus> UpdatesAsync() => _api.GetAsync<UpdatesStatus>("/updates");

    /// <summary>Update to X: the app stops, installs and starts again (the server asks when work would be lost).</summary>
    public Task<JsonElement> UpdateAsync(string version) => _api.PostAsync<JsonElement>("/updates/install", new { version });

    public Task<BetaStatus> BetaAsync() => _api.GetAsync<BetaStatus>("/beta");

    public Task<BetaStatus> SetBetaAsync(bool on) => _api.PutAsync<BetaStatus>("/beta", new { on });

    public Task<JsonElement> ClearBetaLogAsync() => _api.DeleteAsync<JsonElement>("/beta/log");

    public Task<JsonElement> ExportBetaLogAsync(string path) => _api.PostAsync<JsonElement>("/beta/export", new { path });

    public Task<JsonElement> BetaNoteAsync(string text) => _api.PostAsync<JsonElement>("/beta/notes", new { text });

    public Task<ClaudeStatus> ClaudeAsync() => _api.GetAsync<ClaudeStatus>("/claude");

    public Task<ClaudeStatus> SetClaudeBypassAsync(bool bypass) => _api.PutAsync<ClaudeStatus>("/claude", new { bypass });

    public Task<JsonElement> SetEveryFeatureAsync(bool every) => _api.PostAsync<JsonElement>("/app/gates", new { every });
}
