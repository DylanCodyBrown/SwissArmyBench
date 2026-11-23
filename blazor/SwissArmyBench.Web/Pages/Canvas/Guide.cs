namespace SwissArmyBench.Web.Pages.Canvas;

/// <summary>A snapline to draw while a block moves: vertical ("v", at x) or horizontal ("h", at y), spanning the
/// blocks it joins (from, to along the other axis); which of the moving block's lines it is, and what it matches.</summary>
public sealed record Guide(string Axis, double At, double From, double To, string Edge, IReadOnlyList<string> With);
