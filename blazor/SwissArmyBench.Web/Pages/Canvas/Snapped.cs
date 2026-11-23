namespace SwissArmyBench.Web.Pages.Canvas;

/// <summary>A rectangle put on the step, and the guides to draw.</summary>
public sealed record Snapped(BoardRect Rect, IReadOnlyList<Guide> Guides);
