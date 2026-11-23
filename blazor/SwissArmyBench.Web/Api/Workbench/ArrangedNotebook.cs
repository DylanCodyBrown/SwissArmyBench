namespace SwissArmyBench.Web.Api.Workbench;

/// <summary>POST /workbench/tables/arrange: the notebook's cells as they should be, its Tables group in place.</summary>
public sealed record ArrangedNotebook(IReadOnlyList<NotebookCell> Cells, int NextCell);
