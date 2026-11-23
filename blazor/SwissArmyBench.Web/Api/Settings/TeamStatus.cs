namespace SwissArmyBench.Web.Api.Settings;

/// <summary>GET /team: Settings' Team box (no team, or joined: its repository and its sync words), and the folders.</summary>
public sealed record TeamStatus(
    string State,
    bool SyncOn,
    TeamNeeds? Needs,
    string LocalProjects,
    bool LocalProjectsDefault,
    string LibraryFolder,
    bool LibraryDefault,
    string? SharedFolder,
    string? Repository = null,
    string? Url = null,
    TeamSync? Sync = null);
