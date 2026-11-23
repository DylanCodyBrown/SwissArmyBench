namespace SwissArmyBench.Web.Api.Files;

/// <summary>A folder or a file in a folder's listing (GET /folders).</summary>
/// <param name="Name">Its name.</param>
/// <param name="Path">Its real path.</param>
/// <param name="Size">A file's size in bytes.</param>
/// <param name="Modified">When it last changed, in seconds since 1970.</param>
public sealed record FolderEntry(string Name, string Path, long? Size = null, double? Modified = null);
