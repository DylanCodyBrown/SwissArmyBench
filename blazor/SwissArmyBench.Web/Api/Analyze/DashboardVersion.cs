namespace SwissArmyBench.Web.Api.Analyze;

/// <summary>One saved version of a dashboard: its number, when, and its cards.</summary>
public sealed record DashboardVersion(int Version, string Saved, IReadOnlyList<DashboardCard> Cards);
