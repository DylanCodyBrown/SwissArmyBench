namespace SwissArmyBench.Web.Api.Projects;

/// <summary>One of the project's tables on Home's summary: where it came from, its rows and columns (null while it
/// is not read).</summary>
public sealed record SummaryTable(
    string Name,
    string From = "",
    string Kind = "",
    long? Rows = null,
    int? Columns = null);
