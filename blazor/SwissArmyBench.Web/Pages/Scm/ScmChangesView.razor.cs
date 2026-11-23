using Microsoft.AspNetCore.Components;
using Microsoft.AspNetCore.Components.Web;

using SwissArmyBench.Web.Api.Git;

namespace SwissArmyBench.Web.Pages.Scm;

public partial class ScmChangesView
{
    // The message box grows with its lines up to this many pixels (VS Code's).
    private const int LineHeight = 20;
    private const int TallestBox = 134;

    private string? _focused;

    [Parameter]
    public ScmChanges? Changes { get; set; }

    [Parameter]
    public ScmStatus? Status { get; set; }

    [Parameter]
    public ScmRepository? Current { get; set; }

    [Parameter]
    public bool Tree { get; set; }

    [Parameter]
    public ShownDiff? Shown { get; set; }

    [Parameter, EditorRequired]
    public HashSet<string> CollapsedGroups { get; set; } = [];

    /// <summary>Each repository's message box (kept across redraws: a notice, Refresh, a stage).</summary>
    [Parameter, EditorRequired]
    public Dictionary<string, string> Messages { get; set; } = [];

    [Parameter, EditorRequired]
    public ScmPage Host { get; set; } = default!;

    /// <summary>Merge and Staged hidden when empty, as VS Code's; Changes always.</summary>
    private static IEnumerable<(string Id, string Label, IReadOnlyList<ScmResource> Items)> Groups(ScmRepository repo) =>
        new[] { ("merge", "Merge Changes", repo.Groups.Merge), ("index", "Staged Changes", repo.Groups.Index), ("workingTree", "Changes", repo.Groups.WorkingTree) }
            .Where(g => g.Item3.Count > 0 || g.Item1 == "workingTree");

    private static string Scoped(ScmRepository repo, string path) =>
        repo.Scope is { } scope && path.Length > scope.Length ? path[(scope.Length + 1)..] : path;

    /// <summary>A list: the files; a tree: each folder a row, its files under it (VS Code's View as Tree).</summary>
    private IEnumerable<ChangeRow> Rows(ScmRepository repo, IReadOnlyList<ScmResource> items) => Tree
        ? items
            .GroupBy(r => ScmPage.DirName(Scoped(repo, r.Path)))
            .OrderBy(g => g.Key, StringComparer.Ordinal)
            .SelectMany(g => g.Key.Length > 0
                ? g.Select(r => new ChangeRow(null, r, 1)).Prepend(new ChangeRow(g.Key, null, 1))
                : g.Select(r => new ChangeRow(null, r, 0)))
        : items.Select(r => new ChangeRow(null, r, 0));

    private string HeightOf(string which)
    {
        var lines = Messages.GetValueOrDefault(which, string.Empty).Split('\n').Length;
        return $"height: {Math.Min(Math.Max(lines * LineHeight, LineHeight), TallestBox)}px";
    }

    private void Typed(string which, string? text) => Messages[which] = text ?? string.Empty;

    private Task MessageKeyAsync(KeyboardEventArgs e, ScmRepository repo) =>
        e.Key == "Enter" && (e.CtrlKey || e.MetaKey) ? Host.CommitAsync(repo) : Task.CompletedTask;
}
