namespace SwissArmyBench.Web.Api.Grids;

/// <summary>GET /grids: every open grid.</summary>
public sealed record GridsAnswer(IReadOnlyList<GridListItem> Grids);
