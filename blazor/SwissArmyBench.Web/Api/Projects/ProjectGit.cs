namespace SwissArmyBench.Web.Api.Projects;

/// <summary>A project folder's Git branch, read from .git/HEAD (the app never runs git).</summary>
public sealed record ProjectGit(bool Repository = false, string? Branch = null);
