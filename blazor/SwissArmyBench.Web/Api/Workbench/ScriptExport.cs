namespace SwissArmyBench.Web.Api.Workbench;

/// <summary>Export as one Python script… or one notebook…'s answer (POST /workbench/export-script): the file, what
/// cannot be exported (Ask: say so and offer the stubs), the stubs written, the variables it reads, and the
/// paragraph naming a connection that runs only on this computer.</summary>
public sealed record ScriptExport(
    string? Path,
    string File,
    IReadOnlyList<string> Problems,
    IReadOnlyList<string> Lint,
    IReadOnlyList<string> Stubs,
    IReadOnlyList<string> Skipped,
    IReadOnlyList<ScriptExportSetting> Settings,
    string? Ask = null,
    string? LocalWords = null);
