namespace SwissArmyBench.Web.Api.Grids;

/// <summary>GET /grids/{id}/profile (no column): every column's counts, blanks and range, and the duplicate rows.</summary>
public sealed record TableProfile(long Rows, long DuplicateRows, IReadOnlyList<TableProfileColumn> Columns);
