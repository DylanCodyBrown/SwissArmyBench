namespace SwissArmyBench.Web.Api.Projects;

/// <summary>One shared project's sync (GitHub sync's folder status): its commits to push and its conflicts.</summary>
public sealed record ProjectSync(int ToPush = 0, int Conflicts = 0);
