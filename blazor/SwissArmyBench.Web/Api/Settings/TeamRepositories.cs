namespace SwissArmyBench.Web.Api.Settings;

/// <summary>GET /team/repositories: the repositories, newest first.</summary>
public sealed record TeamRepositories(IReadOnlyList<TeamRepository> Repositories);
