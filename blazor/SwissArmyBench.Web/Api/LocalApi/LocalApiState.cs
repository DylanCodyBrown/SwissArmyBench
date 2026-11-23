namespace SwissArmyBench.Web.Api.LocalApi;

/// <summary>GET /local-api: the open project's API.py, its settings, endpoints, problems, targets, whether it runs.</summary>
public sealed record LocalApiState(
    string? Project,
    bool Exists,
    string? File = null,
    LocalApiSettings? Settings = null,
    IReadOnlyList<LocalEndpoint>? Endpoints = null,
    IReadOnlyList<LocalApiProblem>? Problems = null,
    LocalApiRunning? Running = null,
    LocalApiFailed? Failed = null,
    IReadOnlyList<LocalApiTarget>? Targets = null,
    bool AgentWrites = false);
