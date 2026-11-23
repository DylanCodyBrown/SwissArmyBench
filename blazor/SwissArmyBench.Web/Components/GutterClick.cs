namespace SwissArmyBench.Web.Components;

/// <summary>A click in an editor's gutter (the debugger's): its line, and whether it asks for the line's menu (a right
/// click) at a place on the page.</summary>
public sealed record GutterClick(int Line, bool Menu, double X, double Y);
