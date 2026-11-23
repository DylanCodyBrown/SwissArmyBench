namespace SwissArmyBench.Web.Pages.Scm;

/// <summary>One row's view model (VS Code's ISCMHistoryItemViewModel): the item, HEAD, a node or Incoming Changes,
/// and its input and output swimlanes.</summary>
public sealed record GraphRow(
    GraphItem Item,
    string Kind,
    IReadOnlyList<GraphNode> Input,
    IReadOnlyList<GraphNode> Output);
