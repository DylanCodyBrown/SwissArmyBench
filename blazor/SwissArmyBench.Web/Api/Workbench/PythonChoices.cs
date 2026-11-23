namespace SwissArmyBench.Web.Api.Workbench;

/// <summary>GET /workbench/pythons.</summary>
public sealed record PythonChoices(IReadOnlyList<PythonChoice> Pythons);
