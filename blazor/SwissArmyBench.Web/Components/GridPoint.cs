namespace SwissArmyBench.Web.Components;

/// <summary>Where a right-click in the grid was: the row (a view position, or -1 for a header), the column, and the
/// pointer's place on the page (the menu opens there).</summary>
public sealed record GridPoint(long Row, string Column, double X, double Y);
