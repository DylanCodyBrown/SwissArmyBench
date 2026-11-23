namespace SwissArmyBench.Web.Api.Environment;

/// <summary>GET /connections, as the key vaults read it.</summary>
public sealed record KeyVaults(IReadOnlyList<KeyVault> Connections);
