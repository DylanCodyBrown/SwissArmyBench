namespace SwissArmyBench.Web.Pages.Canvas;

/// <summary>The Canvas's two panes (the classic sidePanes.ts): each shown or hidden by its bottom bar button and
/// resized by its left edge, kept per canvas in this browser (a convenience).</summary>
public sealed record CanvasPanes(
    bool Properties = true,
    bool Widgets = true,
    double? PropertiesWidth = null,
    double? WidgetsWidth = null);
