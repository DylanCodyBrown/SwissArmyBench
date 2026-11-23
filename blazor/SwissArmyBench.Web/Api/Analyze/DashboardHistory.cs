namespace SwissArmyBench.Web.Api.Analyze;

/// <summary>GET /dashboards/{name}: its versions.</summary>
public sealed record DashboardHistory(string Name, IReadOnlyList<DashboardVersion> Versions);
