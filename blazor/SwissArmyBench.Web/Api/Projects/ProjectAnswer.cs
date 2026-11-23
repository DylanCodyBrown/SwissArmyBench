namespace SwissArmyBench.Web.Api.Projects;

/// <summary>GET /project: the open project, if any.</summary>
public sealed record ProjectAnswer(ProjectInfo? Project);
