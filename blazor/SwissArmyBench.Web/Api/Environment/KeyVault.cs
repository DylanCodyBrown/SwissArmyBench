namespace SwissArmyBench.Web.Api.Environment;

/// <summary>A key vault as the Settings and secrets tab lists it: its name, kind, whether it loads every secret, its names.</summary>
public sealed record KeyVault(
    string Name,
    string Connection,
    string? Template = null,
    string? Type = null,
    bool Every = false,
    VaultNamesRead? Names = null);
