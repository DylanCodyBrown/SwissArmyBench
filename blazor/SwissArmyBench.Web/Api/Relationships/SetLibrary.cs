namespace SwissArmyBench.Web.Api.Relationships;

/// <summary>GET /relationships/library: every saved set found, the folders searched, the shared ones, and the files
/// that could not be read.</summary>
public sealed record SetLibrary(
    IReadOnlyList<SavedSet> Models,
    IReadOnlyList<string> Folders,
    IReadOnlyList<string> SharedFolders,
    IReadOnlyList<string> Problems);
