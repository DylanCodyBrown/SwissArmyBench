namespace SwissArmyBench.Web.Api.Grids;

/// <summary>POST /grids/{id}/selection-stats: Excel's status bar over the whole selection (counted by the server).
/// IdLike: the number columns that look like identifiers, whose sum would mean nothing.</summary>
public sealed record SelectionStats(
    long Rows,
    long Cells,
    long Count,
    long Numeric,
    double? Sum,
    double? Mean,
    double? Min,
    double? Max,
    IReadOnlyList<string>? IdLike = null);
