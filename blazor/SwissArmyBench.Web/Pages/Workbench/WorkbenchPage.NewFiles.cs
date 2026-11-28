using SwissArmyBench.Web.Api;
using SwissArmyBench.Web.Api.Workbench;
using SwissArmyBench.Web.Components;
using SwissArmyBench.Web.Pages.Workbench.Ide;

namespace SwissArmyBench.Web.Pages.Workbench;

// New file (the owner, 2026-11-27: "turn the + new script on the scripts into a drop down combo that asks what file
// type you wanna create. SQL python json etc. then scaffolds it for you"; then "Everything should get a name or the
// file is not created and yes every file should go scaffolding file on the back. The list of follow-ups available
// should change with projects"). Every way to make a file on these two pages (the top bar's button, the tab strip's
// "+", the landing page, the Files pane's "+", the File menu and the palette, an address: ?new=<type>) goes through
// AskNewAsync: the server's types as they are now (GET /scripts/files/new: they follow the open project's type), the
// one New file dialog with the type preset, and the file written by the server before its tab opens. Cancel makes
// nothing; there is no untitled document.
public partial class WorkbenchPage
{
    private NewFileOptions? _newFileOptions;
    private NewFileButton? _newFileButton;
    private string _newFileStart = string.Empty;
    private string? _askOnceDrawn;

    private async Task LoadNewFileOptionsAsync()
    {
        try
        {
            _newFileOptions = await ScriptIde.NewFileOptionsAsync();
            if (!_newFileOptions.Project && _newFileStart.Length == 0)
            {
                _newFileStart = (await Workbench.HomeAsync()).Folder; // where a loose file starts
            }
        }
        catch (ApiException error)
        {
            _newFileOptions = null;
            _error = error;
        }
    }

    /// <summary>The types this page's New lists: on the Scripts page every one the server names; on the Notebooks
    /// page the ones that open on it (a notebook; what a project's type adds beside it).</summary>
    private IReadOnlyList<NewFileType> NewFileTypes => _newFileOptions is not { } options
        ? []
        : IsNotebooks ? [.. options.Types.Where(t => t.Page == Page)] : options.Types;

    /// <summary>The lines that make something new: one a file type.</summary>
    private IEnumerable<MenuEntry> NewFileEntries() => NewFileMenus.Entries(NewFileTypes, PickNewFileAsync);

    private Task PickNewFileAsync(NewFileType type) => AskNewAsync(type.Id);

    private Task AskNewAsync() => AskNewAsync(null);

    /// <summary>A new file asked for, from anywhere: the dialog for its type (none named: this page's own, a
    /// notebook or the server's default), with the types and folders as they are now.</summary>
    private Task AskNewAsync(string? typeId) => AskNewAsync(typeId, null);

    private async Task AskNewAsync(string? typeId, string? from)
    {
        await LoadNewFileOptionsAsync();
        if (_newFileOptions is not { } options)
        {
            return; // why is on the page
        }
        var wanted = typeId ?? (IsNotebooks ? NewFileTypes.FirstOrDefault()?.Id : options.Default);
        if (options.Types.FirstOrDefault(t => t.Id == wanted) is not { } type)
        {
            _error = new InvalidOperationException(options.Project
                ? $"There is no file type {wanted} in this project."
                : $"Open a project first: {wanted} is made in a project's folder.");
            return;
        }
        StateHasChanged(); // the types and folders reach the dialog
        _newFileButton?.Ask(type, from);
    }

    /// <summary>?new= in the address (a file type): the New file dialog for it once the page is drawn (its name first;
    /// Cancel makes nothing). The address goes back to the page's own, so it never asks twice.</summary>
    private void AskOnceDrawn()
    {
        if (New)
        {
            _askOnceDrawn = NewKind is null or "1" or "true" ? string.Empty : NewKind;
        }
    }

    private async Task AskOnceDrawnAsync()
    {
        if (_askOnceDrawn is not { } asked)
        {
            return;
        }
        _askOnceDrawn = null;
        await AskNewAsync(asked.Length > 0 ? asked : null, NewFrom);
        await FollowAddressAsync();
        StateHasChanged();
    }

    /// <summary>The folder a new file of a type starts in, as the dialog would: the type's own inside the open
    /// project, else (no project open) the Workbench's folder.</summary>
    private async Task<string> NewFileFolderAsync(string typeId)
    {
        await LoadNewFileOptionsAsync();
        return _newFileOptions is { Project: true } options
            ? options.Types.FirstOrDefault(t => t.Id == typeId)?.Folder ?? string.Empty
            : _newFileStart;
    }

    /// <summary>The dialog made the file: it opens as its kind's tab here, on its own page when it has one.</summary>
    private async Task NewFileMadeAsync(NewFileMade made)
    {
        _ = Notes.SayAsync($"Made {made.Relative}.");
        if (made.Address is { Length: > 0 } address)
        {
            Nav.NavigateTo(address);
            return;
        }
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
