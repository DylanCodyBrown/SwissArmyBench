namespace SwissArmyBench.Web.Api.Projects;

/// <summary>GET /git (the Git extension, while it is on): the folders it links, as far as the cards read them.</summary>
public sealed record SyncStatus(IReadOnlyList<SyncFolder> Folders)
{
    /// <summary>The shared projects folder's link, or null.</summary>
    public SyncFolder? Shared => Folders.FirstOrDefault(f => f.Which == "shared");
}
