namespace SwissArmyBench.Web.Api.Variables;

/// <summary>GET /variables, as far as a `${` list reads it.</summary>
public sealed record VariablesOffered(IReadOnlyList<OfferedVariable> Variables);
