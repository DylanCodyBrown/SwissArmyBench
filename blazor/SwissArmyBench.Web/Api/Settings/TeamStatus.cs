namespace SwissArmyBench.Web.Api.Settings;

/// <summary>GET /team: Settings' Team box (no team, or joined), whether GitHub sync is on and signed in, the folders.</summary>
public sealed record TeamStatus(
    string State,
    bool SyncOn,
    string LocalProjects,
    bool LocalProjectsDefault,
    string LibraryFolder,
    bool LibraryDefault,
    string? SharedFolder,
    TeamJoined? Team = null,
    bool SignedIn = false,
    string? Account = null,
    bool Device = false,
    IReadOnlyList<string>? TokenSteps = null,
    TeamPending? Pending = null);
