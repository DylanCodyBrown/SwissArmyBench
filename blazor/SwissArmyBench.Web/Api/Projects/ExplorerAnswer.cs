namespace SwissArmyBench.Web.Api.Projects;

/// <summary>GET /projects/explorer: every project as a card, the types and both projects folders.</summary>
public sealed record ExplorerAnswer(string Folder, string? SharedFolder, string DefaultFolder, IReadOnlyList<ProjectCard> Projects, ExplorerSort Sort, IReadOnlyList<ProjectType> Types, bool Explained);
