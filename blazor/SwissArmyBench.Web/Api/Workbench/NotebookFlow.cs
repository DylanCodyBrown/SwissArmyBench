namespace SwissArmyBench.Web.Api.Workbench;

/// <summary>POST /workbench/notebook/flow: each cell's state from the run order, and the Outline.</summary>
public sealed record NotebookFlow(IReadOnlyList<FlowState> Cells, IReadOnlyList<OutlineItem> Outline);
