namespace SwissArmyBench.Web.Api.Extensions;

/// <summary>An extension's card as the Extensions page draws it: what it adds, its status, a folder extension's path, error and missing packages, its project type, a note, its own panel's route.</summary>
public sealed record ExtensionInfo(
    string Id,
    string Name,
    string Description,
    IReadOnlyList<string> Adds,
    string Status,
    bool Preinstalled = false,
    string? Version = null,
    string? Source = null,
    string? Path = null,
    string? Error = null,
    MissingNeed? Missing = null,
    string? Note = null,
    string? Panel = null,
    string? ProjectType = null,
    string? ProjectName = null,
    IReadOnlyList<string>? Deliverable = null);
