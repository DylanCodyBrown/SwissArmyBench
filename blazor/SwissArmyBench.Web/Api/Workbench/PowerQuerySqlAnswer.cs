namespace SwissArmyBench.Web.Api.Workbench;

/// <summary>Show as SQL's answer: each query asked for, with its composed SQL.</summary>
public sealed record PowerQuerySqlAnswer(IReadOnlyList<PowerQuerySql> Queries);
