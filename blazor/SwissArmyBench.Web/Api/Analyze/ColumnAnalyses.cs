namespace SwissArmyBench.Web.Api.Analyze;

/// <summary>One column of What can I do with a column?: its type, first values, and the analyses that fit it.</summary>
public sealed record ColumnAnalyses(
    string Name,
    string Type,
    IReadOnlyList<string> Preview,
    IReadOnlyList<ColumnFit> Analyses);
