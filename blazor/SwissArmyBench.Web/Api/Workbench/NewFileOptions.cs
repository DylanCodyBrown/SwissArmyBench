namespace SwissArmyBench.Web.Api.Workbench;

/// <summary>GET /scripts/files/new: the file types in the dropdown's order, the one a plain New makes, and the open
/// project's folders (none open: Project false and no folders).</summary>
public sealed record NewFileOptions(
    bool Project,
    IReadOnlyList<NewFileType> Types,
    string Default,
    IReadOnlyList<string> Folders);
