using SwissArmyBench.Web.Api.Workbench;

namespace SwissArmyBench.Web.Pages.Workbench;

// A tab's Rename… (its right click, F2 on the tab, the document's "…"; the owner, 2026-11-24: "we should allow renaming
// here"): a project's module the way the Files pane renames it (its imports following, with the preview), a notebook,
// a SQL file or a loose script renamed in its folder; an untitled one named and saved (Save as, its name first). The
// tab, its title, the address and the recent list follow. Unsaved changes are saved first only on the user's word.
public partial class WorkbenchPage
{
    private async Task RenameTabAsync(int key)
    {
        if (!_byKey.TryGetValue(key, out var doc) || !doc.CanRename)
        {
            return;
        }
        if (doc.Path is null)
        {
            await SaveAsAsync(doc); // its name box first, in the folder a new document saves to
            return;
        }
        if (doc.Dirty)
        {
            if (!await Dialogs.AskYesNoAsync("Rename", $"{doc.Title} has changes that are not saved. Save them, then rename it?", "Save and rename"))
            {
                return;
            }
            await SaveAsync(doc);
            if (doc.Dirty)
            {
                return; // the save did not go through: its reason is on the page
            }
        }
        var path = doc.Path;
        if (TreeFileOf(path) is { Library: true })
        {
            _error = new InvalidOperationException($"{doc.Title} is the library's: it is renamed with its connection or API.");
            return;
        }
        if (IsProjectModule(path))
        {
            _renamingFile = path; // the Files pane's Rename: its imports follow, previewed
            return;
        }
        await RenameInFolderAsync(path);
    }

    /// <summary>A notebook, a SQL file or a loose script renamed in its folder (its new name asked); its tabs follow.</summary>
    private async Task RenameInFolderAsync(string path)
    {
        var current = FilePaths.Name(path);
        var to = await Dialogs.AskTextAsync("Rename", $"Rename {current} to", "New name", current, "Rename");
        if (to is null || to.Trim().Length == 0 || to.Trim() == current)
        {
            return;
        }
        await GuardAsync(async () =>
        {
            var done = await Workbench.RenameAsync(path, to.Trim());
            await FollowRenameAsync(path, done.To);
            await Notes.SayAsync($"Renamed to {FilePaths.Name(done.To)}.");
        });
    }

    private TreeFile? TreeFileOf(string path) =>
        _tree?.Groups.SelectMany(g => g.Files).FirstOrDefault(f => SamePath(f.Full, path));

    /// <summary>A .py of the open project's Files pane (not the library's): a module, renamed with its imports.</summary>
    private bool IsProjectModule(string path) =>
        path.EndsWith(".py", StringComparison.OrdinalIgnoreCase) && TreeFileOf(path) is { Library: false, Module: not null };

    /// <summary>Every tab on a renamed file follows it, then the tree and the address.</summary>
    private async Task FollowRenameAsync(string? from, string to)
    {
        foreach (var doc in _documents.Where(d => d.Path is not null && from is not null && SamePath(d.Path, from)))
        {
            doc.Path = to; // the tab follows its file
        }
        await LoadTreeAsync();
        await FollowAddressAsync();
    }

    /// <summary>A new document's file name for Save as: the page's kind's ending.</summary>
    private static string SuggestedName(OpenDocument doc) => doc.IsSql ? "query.sql" : doc.IsNotebook ? "untitled.ipynb" : "untitled.py";

    /// <summary>The chosen path with the document's kind's ending.</summary>
    private static string WithEnding(OpenDocument doc, string chosen)
    {
        if (doc.IsText)
        {
            return chosen; // a text file keeps the ending it was given
        }
        var ending = doc.IsNotebook ? ".ipynb" : doc.IsSql ? ".sql" : ".py";
        return chosen.EndsWith(ending, StringComparison.OrdinalIgnoreCase) ? chosen : chosen + ending;
    }
}
