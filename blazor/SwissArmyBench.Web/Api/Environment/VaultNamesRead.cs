namespace SwissArmyBench.Web.Api.Environment;

/// <summary>A key vault's names as last read here: how many, when, a failed read's words.</summary>
public sealed record VaultNamesRead(int Count = 0, string? ReadAt = null, string? Error = null);
