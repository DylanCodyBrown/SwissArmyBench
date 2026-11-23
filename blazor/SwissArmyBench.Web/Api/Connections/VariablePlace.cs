namespace SwissArmyBench.Web.Api.Connections;

/// <summary>A variable a connection reads, and where its value comes from (never the value).</summary>
public sealed record VariablePlace(string Name, string From, string? Vault = null, string? Secret = null);
