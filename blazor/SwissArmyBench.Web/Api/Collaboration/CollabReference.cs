namespace SwissArmyBench.Web.Api.Collaboration;

/// <summary>
/// An object a note names (domain/collaboration.py Reference): its kind, its path (a file in the project, a table's or
/// a connection's name), its id (a cell's number, a function, a column) and the text shown. As the server views it:
/// whether its object is gone, the page that shows it; on the picker its link; on the switcher its key and unread.
/// </summary>
public sealed record CollabReference(
    string Kind,
    string Path,
    string Id,
    string Text,
    bool Gone = false,
    string? Href = null,
    string? Key = null,
    int Unread = 0,
    string? Link = null);
