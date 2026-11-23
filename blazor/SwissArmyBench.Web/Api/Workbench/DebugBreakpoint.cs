namespace SwissArmyBench.Web.Api.Workbench;

/// <summary>A breakpoint: its line, and a condition (breaks when true) or a log point's words (prints, never breaks).</summary>
public sealed record DebugBreakpoint(int Line, string? Condition = null, string? Log = null);
