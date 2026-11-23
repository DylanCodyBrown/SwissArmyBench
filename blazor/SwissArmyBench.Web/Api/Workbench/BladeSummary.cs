namespace SwissArmyBench.Web.Api.Workbench;

/// <summary>A blade as the Blades pane lists it (GET /blades, GET /blades/starters).</summary>
public sealed record BladeSummary(
    string Name,
    string Kind,
    string? Variable,
    string? Connection,
    string? Description,
    string? Family,
    IReadOnlyList<string>? Tags = null,
    bool Pinned = false,
    string? Source = null,
    string? Pack = null);
