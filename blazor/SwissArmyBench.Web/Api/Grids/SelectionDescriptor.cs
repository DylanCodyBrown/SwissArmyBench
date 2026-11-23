namespace SwissArmyBench.Web.Api.Grids;

/// <summary>A grid's selection as the server reads it (server/selection.py): row ranges (first and last, both
/// included) and column names; null means every row, or every column.</summary>
public sealed record SelectionDescriptor(IReadOnlyList<long[]>? Rows, IReadOnlyList<string>? Columns);
