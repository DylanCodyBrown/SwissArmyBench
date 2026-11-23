namespace SwissArmyBench.Web.Api.PowerBi;

/// <summary>Export to Power BI's plan (POST /powerbi/plan): the name, where it goes (or a download), each table and relationship, the parameters; after an export what was written and whether it opens.</summary>
public sealed record PowerBiPlan
{
    public string Name { get; init; } = string.Empty;

    public string? Where { get; init; }

    public bool Download { get; init; }

    public IReadOnlyList<PlannedTable> Tables { get; init; } = [];

    public IReadOnlyList<PlannedRelationship> Relationships { get; init; } = [];

    public IReadOnlyList<string> Parameters { get; init; } = [];

    public IReadOnlyList<string> Written { get; init; } = [];

    public IReadOnlyList<string> Removed { get; init; } = [];

    public bool Opens { get; init; }

    public ReportUse? Report { get; init; }
}
