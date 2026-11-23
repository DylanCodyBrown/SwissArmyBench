namespace SwissArmyBench.Web.Pages.Canvas;

/// <summary>A Canvas menu open at a place on the screen.</summary>
public sealed record OpenMenu(double X, double Y, IReadOnlyList<CanvasMenuItem> Items);
