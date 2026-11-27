namespace SwissArmyBench.Web.Api.Canvas;

/// <summary>One top box of a canvas's first page in the desktop layout, for its card's small picture: a container
/// or a widget, X and W fractions of the page's width, Y and H pixels.</summary>
public sealed record CanvasCardBox(string Kind, double X, double Y, double W, double H);
