using SwissArmyBench.Web.Api.Canvas;

namespace SwissArmyBench.Web.Pages.Canvas;

/// <summary>A node being moved or sized: where the press began (page pixels), its container, and whether it has
/// moved past the threshold yet.</summary>
public sealed record Drag(CanvasNode Node, CanvasNode? Parent, bool Sizing, double StartX, double StartY);
