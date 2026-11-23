namespace SwissArmyBench.Web.Api.Workbench;

/// <summary>The Files pane (GET /scripts/tree, GET /project/tree?page=notebooks): its groups of files.</summary>
public sealed record CodeTree(string? Project, string? Folder, IReadOnlyList<TreeGroup> Groups);
