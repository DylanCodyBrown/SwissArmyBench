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

    public Task<TeamWords> TeamActAsync(string route) => _api.PostAsync<TeamWords>(route);

    public Task<TeamWords> TeamLeaveAsync(bool keep) => _api.PostAsync<TeamWords>("/team/leave", new { keep });

    /// <summary>A Join or Start kept over Install's restart (null: gone).</summary>
    public Task TeamPendingAsync(string? action) => _api.PostAsync("/team/pending", new { action });


    public Task<TeamRepositories> TeamRepositoriesAsync() => _api.GetAsync<TeamRepositories>("/team/repositories");

    public Task<TeamMade> TeamJoinAsync(string repository) => _api.PostAsync<TeamMade>("/team/join", new { repository });

    public Task<TeamOwners> TeamOwnersAsync() => _api.GetAsync<TeamOwners>("/team/owners");

    public Task<TeamMade> TeamStartAsync(string name, string? owner) => _api.PostAsync<TeamMade>("/team/start", new { name, owner });

    /// <summary>The library folder pointed at another (null: the default).</summary>
    public Task SetLibraryFolderAsync(string? folder) => _api.PutAsync("/library", new { folder });

    public Task<SetupChecklist> SetupAsync(bool check) => _api.GetAsync<SetupChecklist>(check ? "/library/setup?check=1" : "/library/setup");

    public Task MoveToVaultAsync(string connection, string secret, string vault, string vaultSecret) =>
        _api.PostAsync("/library/setup/move-to-vault", new { connection, secret, vault, vault_secret = vaultSecret });

    /// <summary>A value Set up this computer asks for: a connection's password, a local value, a keyring one.</summary>
    public Task SetupValueAsync(SetupFix fix, string value, string? connection) => fix.Kind switch
    {
        "password" => _api.PutAsync($"/blades/{ApiClient.Part(connection ?? fix.Connection ?? string.Empty)}/secrets", new Dictionary<string, string> { [fix.Name ?? string.Empty] = value }),
        "local" => _api.PutAsync("/variables", new { name = fix.Name, value, local = true }),
        _ => _api.PutAsync("/variables", new { name = fix.Name, value, from = "keyring" }),
    };

    public Task<UpdateStarted> StartUpdateAsync(string version, bool confirmed) =>
        _api.PostAsync<UpdateStarted>("/updates/install", new { version, confirmed });

    public Task<ExportedLog> ExportLogAsync(string path) => _api.PostAsync<ExportedLog>("/beta/export", new { path });

    /// <summary>A note left in beta mode: the words, the place, a picture when asked for.</summary>
    public Task NoteAsync(object note) => _api.PostAsync("/beta/notes", note);

    public Task<ClaudeStatus> ClaudeAsync(bool refresh) => _api.GetAsync<ClaudeStatus>(refresh ? "/claude?refresh=1" : "/claude");

    public Task<ClaudeStatus> SetClaudeAsync(object body) => _api.PutAsync<ClaudeStatus>("/claude", body);

    public Task<ClaudeLaunched> LaunchClaudeAsync(string? app, bool confirmed) =>
        _api.PostAsync<ClaudeLaunched>("/claude/launch", new Dictionary<string, object?> { ["app"] = app, ["confirmed"] = confirmed ? true : null }.Where(p => p.Value is not null).ToDictionary());

    public async Task<IReadOnlyList<Approval>> ApprovalsAsync() => (await _api.GetAsync<Approvals>("/agent/approvals")).Pending;

    public Task AnswerApprovalAsync(string id, bool approve) => _api.PostAsync($"/agent/approvals/{ApiClient.Part(id)}", new { approve });

    public Task<UpdatesStatus> UpdatesAsync() => _api.GetAsync<UpdatesStatus>("/updates");

    /// <summary>Update to X: the app stops, installs and starts again (the server asks when work would be lost).</summary>
    public Task UpdateAsync(string version) => _api.PostAsync("/updates/install", new { version });

    /// <summary>What's New: the releases since the version last seen (opening by itself after an update), or every one.</summary>
    public Task<WhatsNewStatus> WhatsNewAsync(bool all = false) =>
        _api.GetAsync<WhatsNewStatus>(all ? "/whats-new?all=1" : "/whats-new");

    /// <summary>The window closed: the running version is the one last seen on this computer.</summary>
    public Task WhatsNewSeenAsync() => _api.PostAsync("/whats-new/seen");

    public Task<BetaStatus> BetaAsync() => _api.GetAsync<BetaStatus>("/beta");

    public Task<BetaStatus> SetBetaAsync(bool on) => _api.PutAsync<BetaStatus>("/beta", new { on });

    public Task ClearBetaLogAsync() => _api.DeleteAsync("/beta/log");

    public Task ExportBetaLogAsync(string path) => _api.PostAsync("/beta/export", new { path });


    public Task<ClaudeStatus> ClaudeAsync() => _api.GetAsync<ClaudeStatus>("/claude");

    public Task<ClaudeStatus> SetClaudeBypassAsync(bool bypass) => _api.PutAsync<ClaudeStatus>("/claude", new { bypass });

    public Task SetEveryFeatureAsync(bool every) => _api.PostAsync("/app/gates", new { every });
}
