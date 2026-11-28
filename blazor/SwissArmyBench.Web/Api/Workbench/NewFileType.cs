namespace SwissArmyBench.Web.Api.Workbench;

/// <summary>One file type of New file (domain/new_files.py, as data): the list's line, the ending filled in, the
/// folder it starts in, the page it opens on, how its tab is drawn, what its dialog asks (name, folder, connection,
/// variant, source: a file it is made from), its kinds to pick from (a diagram's) and whether it can be made with no project open. The server's list
/// follows the open project's type: the page draws whatever it says and names no type.</summary>
public sealed record NewFileType(
    string Id,
    string Label,
    string Ending,
    IReadOnlyList<string> Endings,
    string Folder,
    string Page,
    string Kind,
    string Icon,
    string Words,
    string Suggested,
    IReadOnlyList<string>? Asks = null,
    IReadOnlyList<NewFileVariant>? Variants = null,
    bool Loose = true)
{
    /// <summary>The dropdown's line: "SQL file (.sql)".</summary>
    public string Line => $"{Label} ({Ending})";

    /// <summary>Does its dialog ask this (folder, connection, variant)? The name is always asked.</summary>
    public bool AsksFor(string what) => (Asks ?? ["name", "folder"]).Contains(what);
}
