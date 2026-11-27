namespace SwissArmyBench.Web.Pages.Workbench.Docs;

/// <summary>Why a diagram could not be drawn: Mermaid's own message and the line it points at (0: none named).</summary>
public sealed record DiagramProblem(string Message, int Line);
