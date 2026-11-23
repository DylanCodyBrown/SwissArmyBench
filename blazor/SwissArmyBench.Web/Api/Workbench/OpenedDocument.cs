namespace SwissArmyBench.Web.Api.Workbench;

/// <summary>POST /workbench/open: a notebook's cells, or a script's text, with what the page needs about it.</summary>
public sealed record OpenedDocument(
    string Path,
    string Kind,
    double Modified,
    IReadOnlyList<NotebookCell>? Cells,
    string? Text,
    string? Python,
    int? NextCell,
    SessionInfo? Session,
    string? Page,
    string? Hash);
