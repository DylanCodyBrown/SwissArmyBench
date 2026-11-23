namespace SwissArmyBench.Web.Api.Workbench;

/// <summary>A search's match in a file: its line, column and line's text.</summary>
public sealed record IdeSearchMatch(int Line, int Column, string Text);
