namespace SwissArmyBench.Web.Api.Projects;

/// <summary>One of a deliverable's files: what it is (<see cref="About"/>) and whether the project has it yet.</summary>
public sealed record DeliverableFile(string Path, string About = "", bool Present = false);
