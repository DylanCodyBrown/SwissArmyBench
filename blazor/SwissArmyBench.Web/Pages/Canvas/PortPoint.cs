namespace SwissArmyBench.Web.Pages.Canvas;

/// <summary>Where a port's dot is on its widget's edge (board pixels): its Ins down the left, Outs and Events down the
/// right.</summary>
public sealed record PortPoint(double X, double Y, string Side);
