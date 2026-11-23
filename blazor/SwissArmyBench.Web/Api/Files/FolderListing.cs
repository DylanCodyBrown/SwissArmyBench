namespace SwissArmyBench.Web.Api.Files;

/// <summary>GET /folders: a folder's subfolders, then its files of the wanted kinds; the first one asked for also its
/// quick places.</summary>
public sealed record FolderListing(
    string Path,
    string? Parent,
    IReadOnlyList<FolderEntry> Folders,
    IReadOnlyList<FolderEntry> Files,
    IReadOnlyList<string> Roots,
    string Home,
    string Separator = "/",
    IReadOnlyList<FolderPlace>? Places = null);
