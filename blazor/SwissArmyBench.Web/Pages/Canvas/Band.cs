using SwissArmyBench.Web.Api.Canvas;

namespace SwissArmyBench.Web.Pages.Canvas;

/// <summary>A container being drawn on empty grid: where the press began, the container it is drawn in (its corner the
/// origin) and the rectangle so far (in that container's pixels).</summary>
public sealed record Band(
    double StartX,
    double StartY,
    CanvasNode? Parent,
    (double X, double Y) Origin,
    BoardRect? Made);
