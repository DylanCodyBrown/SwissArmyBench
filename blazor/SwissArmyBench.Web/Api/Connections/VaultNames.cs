namespace SwissArmyBench.Web.Api.Connections;

/// <summary>POST /connections/vaults/secrets: a vault's secret names (never a value), null when it does not list them.</summary>
public sealed record VaultNames(IReadOnlyList<VaultMapping>? Names);
