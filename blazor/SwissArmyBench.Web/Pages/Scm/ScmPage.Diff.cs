using SwissArmyBench.Web.Api.Git;

namespace SwissArmyBench.Web.Pages.Scm;

/// <summary>The editor part (the classic scmPage.ts showDiff): Monaco's diff editor for a file of a group or of a
/// graph row's commit, the files beside it; a graph row opened shows its files.</summary>
public partial class ScmPage
{
    public Task OpenDiffAsync(ScmRepository repo, ScmResource r, string group)
    {
        var (list, title) = group switch
        {
            "index" => (repo.Groups.Index, "Staged Changes"),
            "merge" => (repo.Groups.Merge, "Merge Changes"),
            _ => (repo.Groups.WorkingTree, "Changes"),
        };
        return ShowDiffAsync(new ShownDiff(repo.Which, r.Path, null, group == "merge", list, title));
    }

    public Task OpenListAsync(ScmRepository repo, IReadOnlyList<ScmResource> items, string title) =>
        items.Count > 0 ? ShowDiffAsync(new ShownDiff(repo.Which, items[0].Path, null, false, items, title)) : Task.CompletedTask;

    public Task OpenFileAsync(ScmRepository repo, ScmResource r) => Notes.SayAsync($"{r.Path} is in {repo.Folder}: open it in its own editor.");

    public async Task ShowDiffAsync(ShownDiff what)
    {
        _shown = what;
        if (await CallAsync(() => Git.DiffAsync(what.Which, what.Path, what.Commit, what.Conflict)) is { } got)
        {
            _diff = got;
        }
        StateHasChanged();
    }

    public void CloseDiff()
    {
        _shown = null;
        _diff = null;
    }

    /// <summary>A graph row opened (its files under it) or closed.</summary>
    public async Task ToggleCommitAsync(ScmRepository repo, string id)
    {
        if (_opened.Remove(id))
        {
            return;
        }
        if (await CallAsync(() => Git.CommitFilesAsync(repo.Which, id)) is { } got)
        {
            _opened[id] = got.Files;
        }
    }
}
