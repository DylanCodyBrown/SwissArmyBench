namespace SwissArmyBench.Web.Api.Blades;

/// <summary>POST /blades/{name}/problems: the lint's problems.</summary>
public sealed record BladeProblems(IReadOnlyList<BladeProblem> Problems);
