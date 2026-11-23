namespace SwissArmyBench.Web.Api.Analyze;

/// <summary>POST /dashboards/{name}/open's answer: the cards opened, and how many show as saved until their tables
/// are open.</summary>
public sealed record DashboardOpened(string Name, int Version, int Cards, int Live, int AsSaved);
