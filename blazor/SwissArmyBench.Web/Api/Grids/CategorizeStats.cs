namespace SwissArmyBench.Web.Api.Grids;

/// <summary>GET /grids/{id}/categorize-stats: a categorize step's rows that matched no rule, and more than one.</summary>
public sealed record CategorizeStats(long Unmatched, long Overlapping);
