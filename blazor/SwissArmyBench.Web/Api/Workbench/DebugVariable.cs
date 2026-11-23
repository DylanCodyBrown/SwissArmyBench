namespace SwissArmyBench.Web.Api.Workbench;

/// <summary>A variable at a stop: its name, value, type, and a reference (above 0: it opens to its parts).</summary>
public sealed record DebugVariable(string Name, string Value, string Type, int Reference);
