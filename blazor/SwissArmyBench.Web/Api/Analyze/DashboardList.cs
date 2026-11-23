namespace SwissArmyBench.Web.Api.Analyze;

/// <summary>GET /dashboards: the saved dashboards.</summary>
public sealed record DashboardList(IReadOnlyList<DashboardSummary> Dashboards);
