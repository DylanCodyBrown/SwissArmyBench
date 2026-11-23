namespace SwissArmyBench.Web.Api.Workbench;

/// <summary>A local sandbox API that would not start: why, and API.py's line.</summary>
public sealed record LocalApiFailed(string Error, int? Line);
