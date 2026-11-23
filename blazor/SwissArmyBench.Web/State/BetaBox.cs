namespace SwissArmyBench.Web.State;

/// <summary>An element's box on the page, in pixels (a beta note's outline while its form is open).</summary>
public sealed record BetaBox(int X, int Y, int W, int H);
