namespace SwissArmyBench.Web.Api.Accounting;

/// <summary>Statements and invoices built (or a dry run): the files, their rows and totals.</summary>
public sealed record BuildPlan
{
    public bool DryRun { get; init; }

    public string Folder { get; init; } = string.Empty;

    public IReadOnlyList<PlanFile> Files { get; init; } = [];

    public int Count { get; init; }

    public IReadOnlyDictionary<string, double> Totals { get; init; } = new Dictionary<string, double>();
}
