using SwissArmyBench.Web.Api.Canvas;

namespace SwissArmyBench.Web.Pages.Canvas;

/// <summary>A node right-clicked at a place on the screen.</summary>
public sealed record NodeMenuAt(CanvasNode Node, double ClientX, double ClientY);
