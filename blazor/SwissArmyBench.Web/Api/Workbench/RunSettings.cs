namespace SwissArmyBench.Web.Api.Workbench;

/// <summary>GET and PUT /workbench/scripts/settings: a script's Run file arguments and each variable it needs, with
/// where each comes from (this computer, a plain value, a key vault's secret by name: never a secret's value).</summary>
public sealed record RunSettings(string Path, string Arguments, IReadOnlyList<RunVariable> Variables);
