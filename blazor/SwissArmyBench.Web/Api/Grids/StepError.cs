namespace SwissArmyBench.Web.Api.Grids;

/// <summary>The step that failed, and why.</summary>
public sealed record StepError(int Index, string Message);
