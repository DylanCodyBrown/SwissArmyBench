using SwissArmyBench.Web.Api;
using SwissArmyBench.Web.Api.Workbench;
using SwissArmyBench.Web.Components;
using SwissArmyBench.Web.Pages.Workbench.Ide;

namespace SwissArmyBench.Web.Pages.Workbench;

// New file (the owner, 2026-11-27: "turn the + new script on the scripts into a drop down combo that asks what file
// type you wanna create. SQL python json etc. then scaffolds it for you"): the Scripts page's top bar and each
// group's "+" list the server's file types (GET /scripts/files/new); a pick opens the New file dialog (its name, the
// folder in the open project, a SQL file's connection), and the file made opens as its kind's tab, a notebook on the
// Notebooks page. With no project open a Python script and a SQL file start untitled, as before.
public partial class WorkbenchPage
{
    // What the dropdown lists until the server's types arrive (or when they cannot be read): the two that start
    // untitled, as before.
    private static readonly IReadOnlyList<NewFileType> _untitledTypes =
    [
        new("python", "Python script", ".py", [".py"], "scripts", "scripts", "script", "python", string.Empty, "untitled"),
        new("sql", "SQL file", ".sql", [".sql"], "scripts", "scripts", "sql", "sql", string.Empty, "query"),
    ];

    private NewFileOptions? _newFileOptions;
    private NewFileButton? _newFileButton;

    private async Task LoadNewFileOptionsAsync()
    {
        if (IsNotebooks)
        {
            return;
        }
        try
        {
            _newFileOptions = await ScriptIde.NewFileOptionsAsync();
        }
        catch (ApiException)
        {
            _newFileOptions = null; // the menu still makes an untitled script and SQL file
        }
    }

    private IReadOnlyList<NewFileType> NewFileTypes => _newFileOptions is { Types.Count: > 0 } options ? options.Types : _untitledTypes;

    /// <summary>The lines that make something new: on the Notebooks page a notebook, on the Scripts page every file
    /// type the server names.</summary>
    private IEnumerable<MenuEntry> NewFileEntries() => IsNotebooks
        ? [new($"New {KindWord}", "notebook", NewAsync)]
        : NewFileMenus.Entries(NewFileTypes, Project.Current is not null, PickNewFileAsync);

    private async Task PickNewFileAsync(NewFileType type)
    {
        if (Project.Current is not null && _newFileOptions is not null)
        {
            await LoadNewFileOptionsAsync(); // the folders as they are now
            StateHasChanged(); // the folders reach the dialog (a menu's line ran this after the page was drawn)
            _newFileButton?.Ask(type); // its name, its folder, a SQL file's connection
            return;
        }
        switch (type.Kind)
        {
            case "sql":
                await NewSqlAsync();
                break;
            case "notebook":
                Nav.NavigateTo("notebooks?new=1");
                break;
            default:
                await NewAsync();
                break;
        }
    }

    /// <summary>The dialog made the file: it opens as its kind's tab here, a notebook on the Notebooks page.</summary>
    private async Task NewFileMadeAsync(NewFileMade made)
    {
        _ = Notes.SayAsync($"Made {made.Relative}.");
        if (made.Page != Page)
        {
            Nav.NavigateTo($"{made.Page}?path={Uri.EscapeDataString(made.Path)}");
            return;
        }
        await OpenPathAsync(made.Path);
        await FollowAddressAsync();
        await LoadTreeAsync();
    }
}
