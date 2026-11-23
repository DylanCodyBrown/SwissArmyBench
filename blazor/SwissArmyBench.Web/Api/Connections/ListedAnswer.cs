namespace SwissArmyBench.Web.Api.Connections;

/// <summary>GET /connections: the saved connections.</summary>
public sealed record ListedAnswer(IReadOnlyList<ListedConnection> Connections);
