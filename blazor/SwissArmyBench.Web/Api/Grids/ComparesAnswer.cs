namespace SwissArmyBench.Web.Api.Grids;

/// <summary>GET /compares: the compares running.</summary>
public sealed record ComparesAnswer(IReadOnlyList<GridCompare> Compares);
