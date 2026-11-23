namespace SwissArmyBench.Web.Api.Grids;

/// <summary>GET /connections: the saved connections.</summary>
public sealed record ConnectionsListing(IReadOnlyList<QueryConnection> Connections);
