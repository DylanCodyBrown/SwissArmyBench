using SwissArmyBench.Web.Api.Workbench;

namespace SwissArmyBench.Web.Pages.Workbench;

// The Files pane's actions on the Scripts page (the classic workbenchIde.ts tree actions): Rename… (a module or a
// package, its imports following, with a preview), Duplicate (a copy beside it, opened), Delete (to the system's
// trash, asked first), New package (its name; in scripts/ or a package's folder). Each file follows everywhere.
public partial class WorkbenchPage
{
    private string? _renamingFile;

    private async Task FileActionAsync((TreeFile? File, string Action) asked)
    {
        var full = asked.File?.Full ?? asked.File?.Path;
        var folder = full is null ? null : System.IO.Path.GetDirectoryName(full);
        await GuardAsync(asked.Action switch
        {
            FilesPane.Rename when full is not null => () => Toggle(() => _renamingFile = full),
            FilesPane.RenamePackage when folder is not null => () => Toggle(() => _renamingFile = folder),
            FilesPane.Duplicate when full is not null => () => DuplicateFileAsync(full),
            FilesPane.Delete when full is not null => () => DeleteFileAsync(full),
            FilesPane.DeletePackage when folder is not null => () => DeleteFileAsync(folder),
            FilesPane.NewPackageHere => () => NewPackageAsync(asked.File is null ? null : folder),
            _ => () => Task.CompletedTask,
        });
    }

    private async Task DuplicateFileAsync(string path)
    {
        var made = await ScriptIde.DuplicateAsync(path);
        await Notes.SayAsync($"Made {System.IO.Path.GetFileName(made.Path)}.");
        await LoadTreeAsync();
        if (made.Path is { } copy)
        {
            await OpenPathAsync(copy);
            await FollowAddressAsync();
        }
    }

    private async Task DeleteFileAsync(string path)
    {
        var name = System.IO.Path.GetFileName(path);
        if (!await Dialogs.AskYesNoAsync($"Delete {name}?", $"{name} goes to the trash.", "Move to the trash", danger: true))
        {
            return;
        }
        var gone = await ScriptIde.DeleteAsync(path);
        await Notes.SayAsync($"{name} is in {gone.To}.");
        await LoadTreeAsync();
    }

    private async Task NewPackageAsync(string? parent)
    {
        if (await Dialogs.AskTextAsync("New package", "A folder with its __init__.py.", "Package name", string.Empty, "Create") is not { Length: > 0 } name)
        {
            return;
        }
        var made = await ScriptIde.NewPackageAsync(name.Trim(), parent);
        await LoadTreeAsync();
        if (made.Path is { } init)
        {
            await OpenPathAsync(init);
            await FollowAddressAsync();
        }
    }

    private async Task RenamedAsync(string to)
    {
        var from = _renamingFile;
        _renamingFile = null;
        foreach (var doc in _documents.Where(d => d.Path is not null && from is not null && SamePath(d.Path, from)))
        {
            doc.Path = to; // the tab follows its file
        }
        await LoadTreeAsync();
        await FollowAddressAsync();
    }

    private async Task OpenAtAsync((string Path, int Line) at)
    {
        await GoToPlaceAsync(new IdePlace(at.Path, at.Line, 1, string.Empty));
    }
}
