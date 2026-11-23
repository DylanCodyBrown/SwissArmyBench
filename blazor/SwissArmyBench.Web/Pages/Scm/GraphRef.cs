namespace SwissArmyBench.Web.Pages.Scm;

/// <summary>A ref on a graph row (VS Code's ISCMHistoryItemRef): its id, name, kind and lane colour (a --vscode-*
/// colour id, or none).</summary>
public sealed record GraphRef(string Id, string Name, string Kind, string? Color = null);
