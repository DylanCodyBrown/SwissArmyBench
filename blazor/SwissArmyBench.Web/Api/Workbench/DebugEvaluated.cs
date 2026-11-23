namespace SwissArmyBench.Web.Api.Workbench;

/// <summary>An expression evaluated in a paused frame (a watch, the debug console): its value or its error.</summary>
public sealed record DebugEvaluated(string? Value = null, string? Error = null);
