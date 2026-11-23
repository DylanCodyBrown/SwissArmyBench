namespace SwissArmyBench.Web.Api.Workbench;

/// <summary>GET /workbench/home: where Save as starts, and the recent files.</summary>
public sealed record WorkbenchHome(string Folder, IReadOnlyList<RecentFile> Recent);
