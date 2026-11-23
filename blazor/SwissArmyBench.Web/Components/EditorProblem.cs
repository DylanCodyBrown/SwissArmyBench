namespace SwissArmyBench.Web.Components;

/// <summary>One problem the editor's lint draws: its line, column and words.</summary>
public sealed record EditorProblem(int Line, int Col, string Message);
