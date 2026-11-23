namespace SwissArmyBench.Web.Api.Projects;

/// <summary>GET /project: the open project, if any; whether open tables are not in a project (loose); a folder
/// another program asked to open while work was unsaved (asked); a folder opened that is not a project yet.</summary>
public sealed record ProjectAnswer(ProjectInfo? Project)
{
    public bool Loose { get; init; }

    public string? Asked { get; init; }

    public string? NotAProject { get; init; }
}
