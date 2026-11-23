namespace SwissArmyBench.Web.Api.Connections;

/// <summary>A variable this computer has, by name, and what gives it (your variables, a key vault): a vault row's check.</summary>
public sealed record TakenVariable(string Name, string From, string? Vault = null, string? Kept = null);
