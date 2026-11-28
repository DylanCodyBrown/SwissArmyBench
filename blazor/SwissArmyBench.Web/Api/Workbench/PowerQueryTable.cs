namespace SwissArmyBench.Web.Api.Workbench;

/// <summary>One open table a Power Query file's run built: its name, the query it came from, its grid, its rows and
/// the file's lines the query spans.</summary>
public sealed record PowerQueryTable(string Table, string Query, string Grid, long Rows, int Line, int EndLine);
