namespace SwissArmyBench.Web.Api.Analyze;

/// <summary>POST /dashboards's answer: the version saved and its cards' count.</summary>
public sealed record DashboardSaved(string Name, int Version, int Cards);
