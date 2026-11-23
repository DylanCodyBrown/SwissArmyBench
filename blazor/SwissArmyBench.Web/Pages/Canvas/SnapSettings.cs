namespace SwissArmyBench.Web.Pages.Canvas;

/// <summary>How a rectangle being drawn, moved or sized snaps: on or off, its step, its box's grid, the other items
/// beside it (their edges and centres), the tolerance in page pixels, and whether it is sized (the left and top edge
/// stay where they are).</summary>
public sealed record SnapSettings(
    bool On,
    SnapStep Step,
    GridSpec Grid,
    IReadOnlyList<BoardRect> Others,
    double Tolerance,
    bool Sizing);
