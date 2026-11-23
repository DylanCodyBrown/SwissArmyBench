namespace SwissArmyBench.Web.Api.Grids;

/// <summary>One table in memory: its name, rows, size, and the grids showing it (none: a closed table).</summary>
public sealed record DatasetEntry(
    string Name,
    long Rows,
    string Size,
    IReadOnlyList<string> Grids,
    bool ChangedOnDisk = false);
