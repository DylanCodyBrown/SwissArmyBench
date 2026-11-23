namespace SwissArmyBench.Web.Api.LocalApi;

/// <summary>The open project's local sandbox API (routes_local_api.py): its state, New, its settings, Run and Stop,
/// a call, its log, Will this work for real?, Export.</summary>
public sealed class LocalApiClient
{
    private readonly ApiClient _api;

    public LocalApiClient(ApiClient api)
    {
        _api = api;
    }

    public Task<LocalApiState> StateAsync() => _api.GetAsync<LocalApiState>("/local-api");

    public Task NewAsync(string? target) => _api.PostAsync("/local-api/new", target is null ? new { } : new { target });

    public Task SettingsAsync(IReadOnlyDictionary<string, string> change) => _api.PutAsync("/local-api/settings", change);

    /// <summary>Run (route "/local-api/run") or Stop ("/local-api/stop").</summary>
    public Task ActAsync(string route) => _api.PostAsync(route, new { });

    public Task StopAgentWritesAsync() => _api.PostAsync("/local-api/agent-writes", new { allow = false });

    public Task<LocalApiLog> LogAsync() => _api.GetAsync<LocalApiLog>("/local-api/log");

    public Task<LocalApiAnswer> CallAsync(string method, string path, IReadOnlyDictionary<string, string> query, object? body) =>
        _api.PostAsync<LocalApiAnswer>("/local-api/call", new { method, path, query, body });

    public Task<RealChecks> CheckAsync() => _api.PostAsync<RealChecks>("/local-api/check", new { });

    public Task<ExportedApi> ExportAsync(string target, bool rows, IReadOnlyList<string>? replace) =>
        _api.PostAsync<ExportedApi>("/local-api/export", new { target, rows, replace });

    /// <summary>New endpoint's plan: the tables, the patterns ranked, a pattern's steps and its code; nothing written.</summary>
    public Task<WizardPlan> PlanAsync(IReadOnlyDictionary<string, object?> asked) => _api.PostAsync<WizardPlan>("/local-api/plan", asked);

    /// <summary>Add to API.py: the pattern's endpoints appended.</summary>
    public Task<Scaffolded> ScaffoldAsync(IReadOnlyDictionary<string, object?> asked) => _api.PostAsync<Scaffolded>("/local-api/scaffold", asked);

    /// <summary>Payload shapes: what each canvas widget that uses an endpoint expects beside what it answers.</summary>
    public Task<PayloadShapes> ShapesAsync() => _api.GetAsync<PayloadShapes>("/local-api/shapes");
}
