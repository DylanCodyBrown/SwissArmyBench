namespace SwissArmyBench.Web.Api.Projects;

/// <summary>One folder GitHub sync links (GET /git): the team library or the shared projects folder.</summary>
/// <param name="Which">library or shared.</param>
/// <param name="Connected">Linked to a repository.</param>
/// <param name="Pulled">Pulled at least once on this computer.</param>
/// <param name="Behind">Commits on GitHub not pulled yet.</param>
/// <param name="Projects">Each shared project's own commits to push and conflicts, by its name.</param>
public sealed record SyncFolder(
    string Which,
    bool Connected = false,
    bool Pulled = false,
    int? Behind = null,
    IReadOnlyDictionary<string, ProjectSync>? Projects = null)
{
    /// <summary>A shared card's words ("↑2 to push", "↓1 behind", "Conflicts: 1"; the classic lazyPages.ts
    /// cardWords), or null when it is up to date or not connected.</summary>
    public string? WordsFor(string project)
    {
        if (!Connected)
        {
            return null;
        }
        var own = Projects?.GetValueOrDefault(project) ?? new ProjectSync();
        return own.Conflicts > 0 ? $"Conflicts: {own.Conflicts}"
            : !Pulled ? "↓ Pull"
            : Behind is > 0 ? $"↓{Behind} behind"
            : own.ToPush > 0 ? $"↑{own.ToPush} to push"
            : null;
    }
}
