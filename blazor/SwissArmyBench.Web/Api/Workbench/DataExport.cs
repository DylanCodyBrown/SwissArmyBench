namespace SwissArmyBench.Web.Api.Workbench;

/// <summary>Export data.py's answer (POST /projects/export-data): where it went, the tables it reads, the ones it
/// cannot read again (FILL IN), and what it said it left out.</summary>
public sealed record DataExport(
    string Path,
    IReadOnlyList<string> Names,
    IReadOnlyList<string> FillIn,
    IReadOnlyList<string> Skipped);
