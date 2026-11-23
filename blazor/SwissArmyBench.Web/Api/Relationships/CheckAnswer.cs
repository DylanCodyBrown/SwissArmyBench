namespace SwissArmyBench.Web.Api.Relationships;

/// <summary>POST /relationships/check: the set checked (or the joins in use) and each join's result.</summary>
public sealed record CheckAnswer(string Set, IReadOnlyList<RunResult> Results);
