namespace SwissArmyBench.Web.Api.Workbench;

/// <summary>One family of the built-in starters (Power BI, Excel, DAX...).</summary>
public sealed record StarterFamily(string Family, IReadOnlyList<BladeSummary> Blades);
