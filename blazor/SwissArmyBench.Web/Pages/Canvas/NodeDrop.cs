using SwissArmyBench.Web.Api.Canvas;

namespace SwissArmyBench.Web.Pages.Canvas;

/// <summary>Something dropped (a widget card) on a container, at a place on the screen.</summary>
public sealed record NodeDrop(CanvasNode Node, double ClientX, double ClientY);
