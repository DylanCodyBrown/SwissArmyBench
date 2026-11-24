namespace SwissArmyBench.Web.Api.Workbench;

/// <summary>What a .sql file's run sends: its file, its text as on screen, where it runs ("" the open tables), and
/// for Run selection the cursor's line and the selected text; the table's name when the file has none yet.</summary>
public sealed record SqlRunRequest(
    string? Path,
    string Text,
    string Connection,
    int? Line = null,
    string? Selection = null,
    string? Table = null);
