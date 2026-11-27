namespace SwissArmyBench.Web.Api.Workbench;

/// <summary>One file type of the Scripts page's New file (domain/new_files.py TYPES, as data): the dropdown's line,
/// the ending filled in, the folder it starts in, the page it opens on and how its tab is drawn.</summary>
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
    string Suggested)
{
    /// <summary>The dropdown's line: "SQL file (.sql)".</summary>
    public string Line => $"{Label} ({Ending})";
}
