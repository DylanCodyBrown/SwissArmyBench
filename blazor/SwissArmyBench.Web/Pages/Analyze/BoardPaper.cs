namespace SwissArmyBench.Web.Pages.Analyze;

/// <summary>A paper Page view lays the board on: its name, its size in pixels (96 to the inch) and as CSS.</summary>
public sealed record BoardPaper(string Label, int Width, int Height, string Css);
