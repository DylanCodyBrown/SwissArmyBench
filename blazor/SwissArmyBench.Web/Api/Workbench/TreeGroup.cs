namespace SwissArmyBench.Web.Api.Workbench;

/// <summary>One group of the Files pane (Your scripts, Project code, the library's Connections...).</summary>
public sealed record TreeGroup(string Id, string Name, IReadOnlyList<TreeFile> Files);
