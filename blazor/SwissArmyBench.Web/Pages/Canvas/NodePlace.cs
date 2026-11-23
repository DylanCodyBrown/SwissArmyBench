using SwissArmyBench.Web.Api.Canvas;

namespace SwissArmyBench.Web.Pages.Canvas;

/// <summary>A node found on the canvas, and the container it is in (null: the page itself).</summary>
public sealed record NodePlace(CanvasNode Node, CanvasNode? Parent);
