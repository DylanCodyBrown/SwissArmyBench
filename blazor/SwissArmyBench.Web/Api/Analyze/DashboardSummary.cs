namespace SwissArmyBench.Web.Api.Analyze;

/// <summary>A saved dashboard: its name, how many versions, when last saved, and its cards' count.</summary>
public sealed record DashboardSummary(string Name, int Versions, string Saved, int Cards);
