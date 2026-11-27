namespace SwissArmyBench.Web.Api.Projects;

/// <summary>One project on the Project Explorer (GET /projects/explorer).</summary>
public sealed record ProjectCard(
    string Path,
    string Name,
    double? Opened,
    bool Open,
    string Where,
    bool Missing,
    string Type,
    string TypeName,
    double? Changed,
    double? Created,
    ProjectCounts Counts,
    IReadOnlyList<string> Documents,
    ProjectGit? Git = null,
    string? CopiedFrom = null);
