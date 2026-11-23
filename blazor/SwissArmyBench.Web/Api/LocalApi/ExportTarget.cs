namespace SwissArmyBench.Web.Api.LocalApi;

/// <summary>The target an export was made for, and how to run it there.</summary>
public sealed record ExportTarget(string Id, string Label, string Run = "");
