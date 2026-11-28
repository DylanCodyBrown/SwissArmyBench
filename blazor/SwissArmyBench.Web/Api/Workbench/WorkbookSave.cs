namespace SwissArmyBench.Web.Api.Workbench;

/// <summary>A save into a workbook, or its preview (POST /scripts/pq/workbook/save and /preview): each query and
/// what happens to it, the one sentence, whether anything was written, and where the one backup copy went.</summary>
public sealed record WorkbookSave(
    string Workbook,
    bool Written,
    bool Writes,
    IReadOnlyList<WorkbookQueryChange> Changes,
    string Words,
    string? Backup = null,
    bool Conflict = false,
    bool OpenInExcel = false);
