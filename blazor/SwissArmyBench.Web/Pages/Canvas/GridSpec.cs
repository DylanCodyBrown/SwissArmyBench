namespace SwissArmyBench.Web.Pages.Canvas;

/// <summary>A box's grid: its columns, the row height, the gap, and the width the columns divide (the page's or a
/// container's).</summary>
public sealed record GridSpec(int Columns, double RowHeight, double Gap, double Width);
