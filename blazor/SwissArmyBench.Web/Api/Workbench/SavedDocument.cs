namespace SwissArmyBench.Web.Api.Workbench;

/// <summary>POST /workbench/save: where it went and the file's time (a later save compares it).</summary>
public sealed record SavedDocument(string Path, double Modified, string? Hash);
