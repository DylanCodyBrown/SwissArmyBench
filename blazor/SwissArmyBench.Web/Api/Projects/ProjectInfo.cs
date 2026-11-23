namespace SwissArmyBench.Web.Api.Projects;

/// <summary>The open project (GET /project's project).</summary>
public sealed record ProjectInfo(
    string Name,
    string Path,
    string Type,
    bool Dirty,
    bool Autosave,
    bool Private = false,
    string? AutosaveError = null,
    string? Folder = null,
    string? ReadOnly = null,
    IReadOnlyList<ProjectProblem>? Problems = null);
