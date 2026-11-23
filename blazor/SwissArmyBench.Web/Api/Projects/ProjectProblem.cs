namespace SwissArmyBench.Web.Api.Projects;

/// <summary>A project's table that did not come back as it opened: why, and its one fix.</summary>
public sealed record ProjectProblem(string Table, string Message, ProblemFix Fix);
