namespace SwissArmyBench.Web.Api.Workbench;

/// <summary>A variable an exported automation reads where it runs, and whether it is a secret.</summary>
public sealed record ScriptExportSetting(string Variable, bool Secret);
