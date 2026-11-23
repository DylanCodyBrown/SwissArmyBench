namespace SwissArmyBench.Web.Pages.Scm;

/// <summary>A commit (or the Incoming Changes row) as the graph draws it (VS Code's ISCMHistoryItem).</summary>
public sealed record GraphItem(
    string Id,
    IReadOnlyList<string> ParentIds,
    string Subject,
    string Author,
    string Date,
    string Message,
    IReadOnlyList<GraphRef> References);
