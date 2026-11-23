namespace SwissArmyBench.Web.Api.Connections;

/// <summary>One secret of a key vault and the variable it sets.</summary>
public sealed record VaultEntry(string Variable, string Secret);
