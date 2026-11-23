namespace SwissArmyBench.Web.Api.Connections;

/// <summary>GET /connections/{name}/access: each app registration's report.</summary>
public sealed record AccessAnswer(IReadOnlyList<AccessBy> Access);
