namespace SwissArmyBench.Web.Api.Settings;

/// <summary>POST /beta/export: where the beta log's zip was written.</summary>
public sealed record ExportedLog(string Path);
