namespace SwissArmyBench.Web.Api.Workbench;

/// <summary>A cell's state in the run order (notRun, edited, outOfDate...) by its number.</summary>
public sealed record FlowState(int Number, string State);
