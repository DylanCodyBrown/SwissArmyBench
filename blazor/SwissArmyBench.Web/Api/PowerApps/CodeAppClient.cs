namespace SwissArmyBench.Web.Api.PowerApps;

/// <summary>The Code App page (the Power Apps extension's /powerapps routes, its own command lines underneath): the
/// state, the tools' Install, the sign-in, the environments, a code app made, opened and closed, its sources, files,
/// pages and data notebook, the connectors, Run live, Push, the versions and a custom connector.</summary>
public sealed class CodeAppClient
{
    private readonly ApiClient _api;

    public CodeAppClient(ApiClient api)
    {
        _api = api;
    }

    public Task<CodeAppState> StateAsync() => _api.GetAsync<CodeAppState>("/powerapps");

    public Task InstallAsync(string tool) => _api.PostAsync("/powerapps/tools/install", new { tool });

    public Task<CodeAppAccount> AccountAsync() => _api.GetAsync<CodeAppAccount>("/powerapps/account");

    public Task<CodeAppAccount> SignInAsync() => _api.PostAsync<CodeAppAccount>("/powerapps/account/sign-in");

    public Task<CodeAppEnvironments> EnvironmentsAsync() => _api.GetAsync<CodeAppEnvironments>("/powerapps/environments");

    public Task<CodeAppProject> NewAsync(string name, string environmentId, string parent) =>
        _api.PostAsync<CodeAppProject>("/powerapps/project/new", new { name, environment_id = environmentId, parent });

    public Task<CodeAppProject> OpenAsync(string folder) => _api.PostAsync<CodeAppProject>("/powerapps/project/open", new { folder });

    public Task<CodeAppProject> CloseAsync() => _api.PostAsync<CodeAppProject>("/powerapps/project/close");

    public Task<CodeAppProject> ProjectAsync() => _api.GetAsync<CodeAppProject>("/powerapps/project");

    /// <summary>One file of the open code app (a code file's tab).</summary>
    public Task<CodeAppFile> FileAsync(string path) => _api.GetAsync<CodeAppFile>($"/powerapps/project/file?path={ApiClient.Part(path)}");

    /// <summary>A code file written back (Save); Run live reloads.</summary>
    public Task SaveFileAsync(string path, string text) => _api.PutAsync("/powerapps/project/file", new { path, text });

    /// <summary>The app's own rule over one file as typed (a page never imports another page's code).</summary>
    public async Task<IReadOnlyList<System.Text.Json.JsonElement>> LintAsync(string path, string text)
    {
        var found = await _api.PostAsync<System.Text.Json.JsonElement>("/powerapps/project/lint", new { path, text });
        return found.TryGetProperty("problems", out var problems) && problems.ValueKind == System.Text.Json.JsonValueKind.Array ? [.. problems.EnumerateArray()] : [];
    }

    public Task<CodeAppFiles> FilesAsync(bool all) => _api.GetAsync<CodeAppFiles>($"/powerapps/project/files{(all ? "?all=1" : string.Empty)}");

    public Task<CodeAppOpened> NewPageAsync(string name) => _api.PostAsync<CodeAppOpened>("/powerapps/pages", new { name });

    public Task<CodeAppOpened> OpenNotebookAsync() => _api.PostAsync<CodeAppOpened>("/powerapps/notebook/open");

    public Task<CodeAppDataTs> UseInAppAsync() => _api.PostAsync<CodeAppDataTs>("/powerapps/notebook/use-in-app");

    public Task<CodeAppGrid> DataverseGridAsync(string source) => _api.PostAsync<CodeAppGrid>("/powerapps/dataverse/grid", new { source });

    public Task<CodeAppProject> AddSourceAsync(IReadOnlyDictionary<string, object?> body) => _api.PostAsync<CodeAppProject>("/powerapps/sources", body);

    public Task<CodeAppProject> RemoveSourceAsync(string name, string connector) => _api.PostAsync<CodeAppProject>("/powerapps/sources/remove", new { name, connector });

    public Task<CodeAppConnectors> ConnectorsAsync(string query, bool refresh) =>
        _api.GetAsync<CodeAppConnectors>($"/powerapps/connectors?q={ApiClient.Part(query)}{(refresh ? "&refresh=1" : string.Empty)}");

    public Task<CodeAppExplored> ConnectorAsync(string name) => _api.GetAsync<CodeAppExplored>($"/powerapps/connectors/{ApiClient.Part(name)}");

    public Task<CodeAppConnections> ConnectionsAsync(string connector) =>
        _api.GetAsync<CodeAppConnections>($"/powerapps/connections?connector={ApiClient.Part(connector)}");

    public Task<CodeAppLive> StartLiveAsync() => _api.PostAsync<CodeAppLive>("/powerapps/live");

    public Task<CodeAppLive> StopLiveAsync() => _api.DeleteAsync<CodeAppLive>("/powerapps/live");

    public Task<CodeAppPushPlan> PushPlanAsync() => _api.PostAsync<CodeAppPushPlan>("/powerapps/push", new { dry_run = true });

    public Task<CodeAppPushed> PushAsync() => _api.PostAsync<CodeAppPushed>("/powerapps/push");

    public Task<CodeAppVersions> VersionsAsync() => _api.GetAsync<CodeAppVersions>("/powerapps/versions");

    public Task<CustomConnectorPlan> CustomConnectorPlanAsync(string api) => _api.PostAsync<CustomConnectorPlan>("/powerapps/custom-connector", new { api, dry_run = true });

    public Task<CustomConnectorMade> MakeCustomConnectorAsync(string api) => _api.PostAsync<CustomConnectorMade>("/powerapps/custom-connector", new { api, dry_run = false });

    public Task<CodeAppRuns> RunsAsync() => _api.GetAsync<CodeAppRuns>("/powerapps/runs");
}
