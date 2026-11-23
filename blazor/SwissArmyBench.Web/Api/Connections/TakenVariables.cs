namespace SwissArmyBench.Web.Api.Connections;

/// <summary>GET /variables, as a vault's form reads it: the names already given.</summary>
public sealed record TakenVariables(IReadOnlyList<TakenVariable> Variables);
