namespace SwissArmyBench.Web.Pages.Grids;

/// <summary>A table opened from a connection with fewer rows than it holds (GridInfo's opened): where it was read
/// from, and how many rows are shown of how many.</summary>
public sealed record OpenedPart(
    string Connection,
    string? Database,
    string? Schema,
    string Table,
    long Shown,
    long Total);
