namespace SwissArmyBench.Web.Api.Analyze;

/// <summary>POST /analyze/column: What can I do with a column? Each column of the table with the analyses that fit it.</summary>
public sealed record ColumnsAnswer(
    string Grid,
    string Dataset,
    string TableLabel,
    long Rows,
    IReadOnlyList<ColumnAnalyses> Columns);
