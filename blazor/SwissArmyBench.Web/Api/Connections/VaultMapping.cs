namespace SwissArmyBench.Web.Api.Connections;

/// <summary>A key vault's secret and the environment variable it is set as.</summary>
public sealed record VaultMapping(string Env, string Secret);
