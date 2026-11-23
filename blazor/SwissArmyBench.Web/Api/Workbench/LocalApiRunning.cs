namespace SwissArmyBench.Web.Api.Workbench;

/// <summary>A local sandbox API running: where, and how many endpoints.</summary>
public sealed record LocalApiRunning(string Url, int Endpoints);
