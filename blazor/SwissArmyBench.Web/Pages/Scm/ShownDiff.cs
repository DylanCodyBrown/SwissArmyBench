using SwissArmyBench.Web.Api.Git;

namespace SwissArmyBench.Web.Pages.Scm;

/// <summary>The file the diff editor shows: its repository, path, commit (a graph row's) or merge conflict, the list
/// it belongs to (the files beside the editor) and that list's title.</summary>
public sealed record ShownDiff(
    string Which,
    string Path,
    string? Commit,
    bool Conflict,
    IReadOnlyList<ScmResource> List,
    string Title);
