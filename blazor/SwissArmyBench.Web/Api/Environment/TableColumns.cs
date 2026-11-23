namespace SwissArmyBench.Web.Api.Environment;

/// <summary>GET /environment/columns: a table's columns with their ranges and blanks, each [name, type, words].</summary>
public sealed record TableColumns(IReadOnlyList<IReadOnlyList<string>> Columns);
