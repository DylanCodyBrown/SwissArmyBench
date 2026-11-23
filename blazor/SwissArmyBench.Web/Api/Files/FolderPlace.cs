namespace SwissArmyBench.Web.Api.Files;

/// <summary>A quick place of the page's own picker: Home, Desktop, Documents, Downloads, Projects, Library, a recent
/// folder of this kind of pick, a drive.</summary>
/// <param name="Name">Its words.</param>
/// <param name="Path">Its real path.</param>
/// <param name="Kind">home, desktop, documents, downloads, projects, library, recent or drive.</param>
public sealed record FolderPlace(string Name, string Path, string Kind);
