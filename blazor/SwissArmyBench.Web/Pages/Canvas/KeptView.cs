namespace SwissArmyBench.Web.Pages.Canvas;

/// <summary>What a canvas was left with in this browser: its layout, each layout's preview width and the zoom.</summary>
public sealed record KeptView(string Layout, double Desktop, double Phone, double Zoom);
