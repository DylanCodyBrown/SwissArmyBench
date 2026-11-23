using Microsoft.JSInterop;

using SwissArmyBench.Web.Api.Git;

namespace SwissArmyBench.Web.Pages.Scm;

/// <summary>The Source Control page's actions (the classic scmPage.ts [the actions]): stage and unstage, discard
/// (asked in VS Code's words), commit (VS Code's smart commit asked once), pull, push, sync, fetch, disconnect,
/// checkout and Create Branch..., Clone Repository and Connect Folder to Repository.</summary>
public partial class ScmPage
{
    private const string SmartCommitKey = "scm.smartCommit";

    /// <summary>An action, then its words as a note (when it answers words), then everything read again.</summary>
    private async Task AfterAsync(Func<Task<ScmWords>> action)
    {
        if (await CallAsync(action) is { } done && done.Words.Length > 0)
        {
            await Notes.SayAsync(done.Words);
        }
        await LoadAsync();
    }

    public async Task StageAsync(ScmRepository repo, IEnumerable<string> paths, bool unstage = false)
    {
        await CallAsync(() => Git.StageAsync(repo.Which, paths.ToList(), unstage));
        await LoadAsync();
    }

    public async Task DiscardAsync(ScmRepository repo, IReadOnlyList<ScmResource> items)
    {
        if (items.Count == 0)
        {
            return;
        }
        var one = items.Count == 1 ? items[0] : null;
        var untracked = one is { Letter: "U" or "A" };
        var name = one is null ? string.Empty : BaseName(one.Path);
        var message = one is null
            ? $"Are you sure you want to discard ALL changes in {items.Count} files?"
            : untracked
                ? $"Are you sure you want to DELETE {name}?\nThis is IRREVERSIBLE!\nThis file will be FOREVER LOST if you proceed."
                : $"Are you sure you want to discard changes in '{name}'?";
        var detail = one is not null && !untracked ? string.Empty : "This is IRREVERSIBLE!\nYour current working set will be FOREVER LOST if you proceed.";
        var button = untracked ? "Delete File" : one is not null ? "Discard File" : $"Discard All {items.Count} Files";
        if (await AskAsync(message, detail, button) is null)
        {
            return;
        }
        await CallAsync(() => Git.DiscardAsync(repo.Which, items.Select(r => r.Path).ToList()));
        await LoadAsync();
    }

    /// <summary>Commit (which: staged or all); nothing staged: VS Code's smart commit asks to stage all (Always
    /// remembered); no message: the box takes the focus and the note says so.</summary>
    public async Task CommitAsync(ScmRepository repo, string? which = null, bool syncFirst = false)
    {
        var message = _messages.GetValueOrDefault(repo.Which, string.Empty).Trim();
        var staged = repo.Groups.Index.Select(r => r.Path).ToList();
        IReadOnlyList<string> paths = staged;
        if (which == "all" || (staged.Count == 0 && which != "staged"))
        {
            if (repo.Groups.WorkingTree.Count == 0 && staged.Count == 0)
            {
                await AskAsync("There are no changes to commit.", string.Empty, "OK");
                return;
            }
            if (staged.Count == 0 && which != "all" && await Js.InvokeAsync<string?>("sab.recall", SmartCommitKey) != "always")
            {
                var picked = await AskAsync("There are no staged changes to commit.", "Would you like to stage all your changes and commit them directly?", "Yes", "Always", "Never");
                if (picked is null or "Never")
                {
                    return;
                }
                if (picked == "Always")
                {
                    await Js.InvokeVoidAsync("sab.remember", SmartCommitKey, "always");
                }
            }
            paths = [.. staged, .. repo.Groups.WorkingTree.Select(r => r.Path)];
        }
        if (message.Length == 0)
        {
            await Js.InvokeVoidAsync("sab.focus", $"textarea[data-which=\"{repo.Which}\"]");
            Notes.Error(new InvalidOperationException("Please provide a commit message"));
            return;
        }
        if (await CallAsync(() => Git.CommitAsync(repo.Which, message, paths, syncFirst)) is { } done)
        {
            await Notes.SayAsync(done.Words);
            _messages.Remove(repo.Which);
            _histories.Remove(repo.Which);
        }
        await LoadAsync();
    }

    public async Task PullAsync(string which)
    {
        await AfterAsync(() => Git.PullAsync(which));
        _histories.Remove(which);
    }

    public Task PushAsync(string which) => AfterAsync(() => Git.PushAsync(which));

    public Task SyncAsync(string which) => AfterAsync(() => Git.SyncAsync(which));

    public async Task FetchAsync()
    {
        await CallAsync(() => Git.StatusAsync(remote: true));
        _histories.Clear();
        await LoadAsync();
    }

    private async Task DisconnectAsync(string which)
    {
        await CallAsync(() => Git.DisconnectAsync(which));
        await LoadAsync();
    }

    public async Task CheckoutToAsync(ScmRepository repo)
    {
        if (await CallAsync(() => Git.BranchesAsync(repo.Which)) is not { } got)
        {
            return;
        }
        const string Create = "\0create";
        var choices = got.Branches.Select(b => new PickChoice(b.Name, b.Name, b.Commit[..Math.Min(8, b.Commit.Length)])).Prepend(new PickChoice("+ Create new branch...", Create)).ToList();
        var picked = await PickAsync("Select a ref to checkout", choices);
        if (picked == Create)
        {
            await CreateBranchAsync(repo);
        }
        else if (picked is not null && picked != got.Current)
        {
            await AfterAsync(() => Git.CheckoutAsync(repo.Which, picked, create: false));
        }
    }

    public async Task CreateBranchAsync(ScmRepository repo)
    {
        if (await PickAsync("Please provide a new branch name", [], free: true) is { } name)
        {
            await AfterAsync(() => Git.CheckoutAsync(repo.Which, name, create: true));
        }
    }

    private async Task<string?> PickRepositoryAsync()
    {
        if (await CallAsync(Git.RepositoriesAsync) is not { } got)
        {
            return null;
        }
        var choices = got.Repositories.Select(r => new PickChoice(r.Repository, r.Repository, r.Private ? "Private" : "Public")).ToList();
        return await PickAsync("Provide repository URL or pick a repository source.", choices, free: true);
    }

    private Task<string?> PickWhichAsync() => PickAsync("Pick the folder",
    [
        new PickChoice("Team library folder", "library", "connections, variables, the shared catalog"),
        new PickChoice("Shared projects folder", "shared", "your team's projects"),
    ]);

    public async Task CloneAsync()
    {
        if (await PickRepositoryAsync() is not { } repository || await PickWhichAsync() is not { } which)
        {
            return;
        }
        if (await Files.ChooseAsync("folder", $"Choose a folder to clone {repository} into") is not { } folder)
        {
            return;
        }
        if (await CallAsync(() => Git.CloneAsync(which, repository, folder)) is { } done)
        {
            var words = which == "library" ? "team library folder" : "shared projects folder";
            await Notes.SayAsync($"Cloned {repository}: {done.Files} files. It is the {words} now.");
        }
        await LoadAsync();
    }

    public async Task ConnectAsync()
    {
        if (await PickWhichAsync() is not { } which || await PickRepositoryAsync() is not { } repository)
        {
            return;
        }
        if (await CallAsync(() => Git.ConnectAsync(which, repository)) is { } done)
        {
            await Notes.SayAsync(done.Words);
        }
        await LoadAsync();
    }

    public static string BaseName(string path) => path.Split('/')[^1];

    public static string DirName(string path) => path.Contains('/', StringComparison.Ordinal) ? path[..path.LastIndexOf('/')] : string.Empty;
}
