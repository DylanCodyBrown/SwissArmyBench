using Microsoft.AspNetCore.Components.Web;
using Microsoft.JSInterop;

using SwissArmyBench.Web.Api.Git;

namespace SwissArmyBench.Web.Pages.Scm;

/// <summary>The Source Control page's menus (the classic scmPage.ts moreMenu, buttonRow, groupRow and resourceMenu):
/// VS Code's own lines; what needs a local Git is greyed out.</summary>
public partial class ScmPage
{
    private void MoreMenu(MouseEventArgs e, ScmRepository repo) => Menu(e.ClientX, e.ClientY + 12, "More Actions...", MoreItems(repo));

    public IReadOnlyList<ScmMenuItem?> MoreItems(ScmRepository repo)
    {
        var which = repo.Which;
        static ScmMenuItem Off(string label) => ScmMenuItem.Off(label);
        return
        [
            new("Pull", () => PullAsync(which)),
            new("Push", () => PushAsync(which)),
            new("Clone", CloneAsync),
            new("Checkout to...", () => CheckoutToAsync(repo)),
            new("Fetch", FetchAsync),
            null,
            new("Commit", Submenu:
            [
                new("Commit", () => CommitAsync(repo)),
                new("Commit Staged", () => CommitAsync(repo, "staged")),
                new("Commit All", () => CommitAsync(repo, "all")),
                Off("Undo Last Commit"), Off("Abort Rebase"), null,
                Off("Commit (Amend)"), Off("Commit Staged (Amend)"), Off("Commit All (Amend)"), null,
                Off("Commit (Signed Off)"), Off("Commit Staged (Signed Off)"), Off("Commit All (Signed Off)"),
            ]),
            new("Changes", Submenu:
            [
                new("Stage All Changes", () => StageAsync(repo, repo.Groups.WorkingTree.Select(r => r.Path))),
                new("Unstage All Changes", () => StageAsync(repo, repo.Groups.Index.Select(r => r.Path), unstage: true)),
                new("Discard All Changes", () => DiscardAsync(repo, repo.Groups.WorkingTree)),
            ]),
            new("Pull, Push", Submenu:
            [
                new("Sync", () => SyncAsync(which)), Off("Sync (Rebase)"), null,
                new("Pull", () => PullAsync(which)), Off("Pull (Rebase)"), Off("Pull from..."), null,
                new("Push", () => PushAsync(which)), Off("Push to..."), null,
                new("Fetch", FetchAsync), Off("Fetch (Prune)"), Off("Fetch From All Remotes"),
            ]),
            new("Branch", Submenu:
            [
                Off("Merge..."), Off("Rebase Branch..."), null,
                new("Create Branch...", () => CreateBranchAsync(repo)), Off("Create Branch From..."), null,
                Off("Rename Branch..."), Off("Delete Branch..."), Off("Delete Remote Branch..."), null,
                Off("Publish Branch..."),
            ]),
            new("Remote", Submenu: [Off("Add Remote..."), Off("Remove Remote")]),
            new("Stash", Submenu:
            [
                Off("Stash"), Off("Stash (Include Untracked)"), Off("Stash Staged"), Off("Apply Latest Stash"), Off("Apply Stash..."),
                Off("Pop Latest Stash"), Off("Pop Stash..."), Off("Drop Stash..."), Off("Drop All Stashes..."),
            ]),
            new("Tags", Submenu: [Off("Create Tag"), Off("Delete Tag..."), Off("Delete Remote Tag...")]),
            new("Worktrees", Submenu: [Off("Create Worktree..."), Off("Delete Worktree...")]),
            null,
            new("Disconnect from GitHub", () => DisconnectAsync(which)),
            Off("Show Git Output"),
        ];
    }

    /// <summary>The Commit button's ▾.</summary>
    public IReadOnlyList<ScmMenuItem?> CommitItems(ScmRepository repo) =>
    [
        new("Commit", () => CommitAsync(repo)),
        ScmMenuItem.Off("Commit (Amend)"),
        null,
        new("Commit & Push", () => CommitAsync(repo)),
        new("Commit & Sync", () => CommitAsync(repo, syncFirst: true)),
    ];

    public IReadOnlyList<ScmMenuItem?> GroupItems(ScmRepository repo, string group, IReadOnlyList<ScmResource> items) => group switch
    {
        "index" => [new("Unstage All Changes", () => StageAsync(repo, items.Select(r => r.Path), unstage: true))],
        "merge" => [new("Stage All Merge Changes", () => StageAsync(repo, items.Select(r => r.Path)))],
        _ => [new("Discard All Changes", () => DiscardAsync(repo, items)), new("Stage All Changes", () => StageAsync(repo, items.Select(r => r.Path)))],
    };

    public IReadOnlyList<ScmMenuItem?> ResourceItems(ScmRepository repo, string group, ScmResource r)
    {
        var open = new ScmMenuItem("Open Changes", () => OpenDiffAsync(repo, r, group));
        var file = new ScmMenuItem("Open File", () => OpenFileAsync(repo, r));
        var head = new ScmMenuItem("Open File (HEAD)", () => OpenDiffAsync(repo, r, group), Disabled: r.Status is "untracked" or "index_added");
        var reveal = ScmMenuItem.Off("Reveal in File Explorer View");
        return group switch
        {
            "index" => [open, file, head, null, new("Unstage Changes", () => StageAsync(repo, [r.Path], unstage: true)), null, reveal],
            "merge" => [file, null, new("Stage Changes", () => StageAsync(repo, [r.Path])), new("Accept Theirs (Open Changes)", () => OpenDiffAsync(repo, r, group))],
            _ =>
            [
                open, head, file, null,
                new("Stage Changes", () => StageAsync(repo, [r.Path])),
                new("Discard Changes", () => DiscardAsync(repo, [r])),
                ScmMenuItem.Off("Add to .gitignore"),
                null,
                reveal,
            ],
        };
    }

    /// <summary>A graph row's menu: Create Branch... on the commit synced here, Copy Commit Hash and Message.</summary>
    public IReadOnlyList<ScmMenuItem?> CommitRowItems(ScmRepository repo, GraphItem item) =>
    [
        ScmMenuItem.Off("Checkout (Detached)"),
        new("Create Branch...", () => CreateBranchAsync(repo), Disabled: item.Id != repo.Commit),
        ScmMenuItem.Off("Create Tag..."),
        null,
        ScmMenuItem.Off("Cherry Pick"),
        null,
        ScmMenuItem.Off("Compare with Remote"),
        ScmMenuItem.Off("Compare with Merge Base"),
        ScmMenuItem.Off("Compare with..."),
        null,
        new("Copy Commit Hash", () => CopyAsync(item.Id)),
        new("Copy Commit Message", () => CopyAsync(item.Message)),
    ];

    private async Task CopyAsync(string text) => await Js.InvokeAsync<bool>("sab.copy", text);
}
