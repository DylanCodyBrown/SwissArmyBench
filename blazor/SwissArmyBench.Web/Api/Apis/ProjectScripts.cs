namespace SwissArmyBench.Web.Api.Apis;

/// <summary>GET /project/documents?kind=script: the open project's scripts.</summary>
public sealed record ProjectScripts(string? Project, IReadOnlyList<ProjectScript> Documents);
