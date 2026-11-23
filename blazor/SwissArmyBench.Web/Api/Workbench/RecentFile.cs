namespace SwissArmyBench.Web.Api.Workbench;

/// <summary>A notebook or script opened before (its whole path, when, and whether it is still there).</summary>
public sealed record RecentFile(string Path, double Opened, bool Exists);
