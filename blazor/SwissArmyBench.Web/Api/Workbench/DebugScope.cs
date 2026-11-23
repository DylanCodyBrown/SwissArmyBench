namespace SwissArmyBench.Web.Api.Workbench;

/// <summary>A frame's scope (Locals, Globals) and its variables.</summary>
public sealed record DebugScope(string Scope, IReadOnlyList<DebugVariable> Variables);
