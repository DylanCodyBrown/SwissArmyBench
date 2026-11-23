namespace SwissArmyBench.Web.Api.Workbench;

/// <summary>A failed run taken apart by the server (domain/errors.py, a run's error_detail): the chain of errors,
/// the last the one that stopped the run, and where in the user's code.</summary>
public sealed record RunError(IReadOnlyList<RunErrorEntry> Chain, string? Where = null);
