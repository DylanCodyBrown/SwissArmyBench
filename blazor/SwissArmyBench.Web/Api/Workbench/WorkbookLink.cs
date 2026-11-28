namespace SwissArmyBench.Web.Api.Workbench;

/// <summary>What a Power Query file linked to an Excel workbook shows (POST /scripts/pq/workbook): the workbook by
/// name, whether it is there, how many queries it holds, whether Excel has it open, whether its queries changed on
/// disk since the file was opened, and why it cannot be read or saved into (one sentence). CanAdd: the workbook has no
/// Power Query yet, and a save may add it on the user's own click, never by itself.</summary>
public sealed record WorkbookLink(
    bool Linked,
    string? Workbook = null,
    string? WorkbookPath = null,
    bool There = true,
    int Queries = 0,
    bool OpenInExcel = false,
    bool Changed = false,
    string? Why = null,
    bool CanAdd = false);
