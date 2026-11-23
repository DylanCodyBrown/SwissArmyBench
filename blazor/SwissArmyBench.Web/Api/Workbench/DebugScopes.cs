namespace SwissArmyBench.Web.Api.Workbench;

/// <summary>POST /workbench/debug/variables for a frame: its scopes; for a reference: its parts.</summary>
public sealed record DebugScopes(IReadOnlyList<DebugScope>? Scopes = null, IReadOnlyList<DebugVariable>? Variables = null);
