namespace SwissArmyBench.Web.Api.Projects;

/// <summary>Each section's count on Home's summary.</summary>
public sealed record SummaryCounts(
    int Tables = 0,
    int Notebooks = 0,
    int Scripts = 0,
    int Apps = 0,
    int Structures = 0,
    int Connections = 0);
