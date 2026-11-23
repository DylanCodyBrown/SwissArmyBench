namespace SwissArmyBench.Web.Api.Grids;

/// <summary>GET /grids/{id}/values: a column's values with their row counts (the filter's checklist), whether there
/// are more than listed, and how many are blank.</summary>
public sealed record ValueList(IReadOnlyList<ValueCount> Values, bool More, long Blanks);
