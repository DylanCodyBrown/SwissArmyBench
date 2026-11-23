namespace SwissArmyBench.Web.Components;

/// <summary>A breakpoint drawn in an editor's gutter: its line, its kind (plain, condition, log) and its words.</summary>
public sealed record BreakpointMark(int Line, string Kind, string Title);
