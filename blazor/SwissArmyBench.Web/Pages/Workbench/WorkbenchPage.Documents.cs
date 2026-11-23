using Microsoft.JSInterop;

using SwissArmyBench.Web.Api;
using SwissArmyBench.Web.Api.Workbench;
using SwissArmyBench.Web.Pages.Workbench.Tabs;

namespace SwissArmyBench.Web.Pages.Workbench;

// The documents as tabs: opened from the address or Open…, new, shown, closed (asked first when unsaved), saved and
// saved as (the classic workbenchPage.ts open, show, close and save).
public partial class WorkbenchPage
{
    private const string SplitWhy = "its group has only this tab: open another first";

    private async Task OpenPathAsync(string path)
    {
        var notebook = path.EndsWith(".ipynb", StringComparison.OrdinalIgnoreCase);
        if (notebook != IsNotebooks)
        {
            // A file opens on its kind's page (the classic workbench_pages.py's one line).
            var page = notebook ? "notebooks" : "scripts";
            _wrongPage = ($"{System.IO.Path.GetFileName(path)} is a {(notebook ? "notebook" : "script")}: it opens on the {(notebook ? "Notebooks" : "Scripts")} page.", $"{page}?path={Uri.EscapeDataString(path)}");
            return;
        }
        if (_documents.FirstOrDefault(d => string.Equals(d.Path, path, StringComparison.OrdinalIgnoreCase)) is { } open)
        {
            _layout.Show(open.Key); // already a tab: brought to the front
            return;
        }
        _loading = true;
        try
        {
            var doc = new OpenDocument(++_nextKey, notebook);
            if (notebook)
            {
                doc.Notebook = await Workbench.OpenNotebookAsync(path);
                (doc.Path, doc.Modified) = (doc.Notebook.Path, doc.Notebook.Modified);
            }
            else
            {
                var script = await Workbench.OpenScriptAsync(path);
                (doc.Path, doc.Modified, doc.ScriptText) = (script.Path, script.Modified, script.Text);
            }
            AddDocument(doc);
            _error = null;
        }
        catch (ApiException error)
        {
            _error = error;
        }
        _loading = false;
    }

    private void AddDocument(OpenDocument doc)
    {
        _documents.Add(doc);
        _byKey[doc.Key] = doc;
        _layout.Add(doc.Key);
    }

    private int NextUntitled() => _documents.Where(d => d.Path is null).Select(d => d.Untitled).DefaultIfEmpty(0).Max() + 1;

    /// <summary>A tab brought to the front: the address follows it (replaced, so Back leaves the page).</summary>
    private async Task ShowAsync(int key)
    {
        _layout.Show(key);
        await FollowAddressAsync();
    }

    private Task ShowNextAsync(int by) => _layout.NextTab(by) is { } key ? ShowAsync(key) : Task.CompletedTask;

    private async Task FollowAddressAsync()
    {
        var path = Front?.Path;
        _shownFor = $"{path}|{path is null && Front is not null}";
        Nav.NavigateTo(path is null ? (Front is null ? Page : $"{Page}?new=1") : $"{Page}?path={Uri.EscapeDataString(path)}", replace: true);
        await Js.InvokeVoidAsync("sab.setTitle", Title);
    }

    /// <summary>A tab closed; one with unsaved changes is asked about first.</summary>
    private async Task CloseAsync(int key)
    {
        if (!_byKey.TryGetValue(key, out var doc))
        {
            return;
        }
        if (doc.Dirty && !await Dialogs.AskYesNoAsync("Close", $"{doc.Title} has changes that are not saved. Close it anyway?", "Close", danger: true))
        {
            return;
        }
        _layout.Remove(key);
        _documents.Remove(doc);
        _byKey.Remove(key);
        _problems.Remove(key);
        if (_documents.Count == 0)
        {
            _recent = await RecentAsync();
        }
        await FollowAddressAsync();
    }

    private async Task SplitAsync(OpenDocument? doc, SplitSide side)
    {
        if (doc is null || !_layout.Split(doc.Key, side))
        {
            _error = new InvalidOperationException($"It cannot split: {SplitWhy}.");
            return;
        }
        await Task.CompletedTask;
    }

    private Task NewAsync()
    {
        AddDocument(new OpenDocument(++_nextKey, IsNotebooks) { Untitled = NextUntitled() });
        return FollowAddressAsync();
    }

    private async Task OpenAsync()
    {
        var home = await Workbench.HomeAsync();
        if (await Files.ChooseAsync("file", $"Open a {KindWord}", home.Folder, Kind) is { } path)
        {
            var notebook = path.EndsWith(".ipynb", StringComparison.OrdinalIgnoreCase);
            if (notebook == IsNotebooks)
            {
                await OpenPathAsync(path);
                await FollowAddressAsync();
            }
            else
            {
                Nav.NavigateTo($"{(notebook ? "notebooks" : "scripts")}?path={Uri.EscapeDataString(path)}");
            }
        }
    }

    private void MarkDirty(OpenDocument doc) => doc.Dirty = true;

    private void ScriptChanged(OpenDocument doc, string text)
    {
        doc.Dirty = doc.Dirty || text != doc.ScriptText;
        doc.ScriptText = text;
    }

    /// <summary>The top bar's Save: the document in front, else the open project's .sab/ state.</summary>
    private async Task SaveFrontAsync()
    {
        if (Front is { } doc)
        {
            await SaveAsync(doc);
        }
        else if (Project.Current is not null)
        {
            await GuardAsync(SaveProjectAsync);
        }
    }

    private async Task SaveProjectAsync()
    {
        await ProjectsApi.SaveAsync();
        await Project.RefreshAsync();
        await Notes.SayAsync("Saved");
    }

    private Task SaveAsync(OpenDocument? doc) => doc is null ? Task.CompletedTask : doc.Path is null ? SaveAsAsync(doc) : SaveToAsync(doc, doc.Path);

    private async Task SaveAsAsync(OpenDocument? doc)
    {
        if (doc is null)
        {
            return;
        }
        var home = await Workbench.HomeAsync();
        var start = doc.Path is null ? home.Folder : System.IO.Path.GetDirectoryName(doc.Path);
        if (await Files.ChooseAsync("save", "Save as", start, Kind) is not { } chosen)
        {
            return;
        }
        var extension = doc.IsNotebook ? ".ipynb" : ".py";
        await SaveToAsync(doc, chosen.EndsWith(extension, StringComparison.OrdinalIgnoreCase) ? chosen : chosen + extension);
    }

    private async Task SaveToAsync(OpenDocument doc, string path, bool force = false)
    {
        try
        {
            var renamed = path != doc.Path;
            var saved = await SaveCallAsync(doc, path, renamed ? null : doc.Modified, force);
            (doc.Path, doc.Modified, doc.Dirty) = (saved.Path, saved.Modified, false);
            _error = null;
            _ = Notes.SayAsync($"Saved {doc.Title}.");
            if (renamed && doc == Front)
            {
                await FollowAddressAsync();
            }
            await LoadTreeAsync();
        }
        catch (ApiException error) when (error.Status == ConflictStatus && !force)
        {
            // Changed on disk since it was read: the file is replaced only on the user's word.
            if (await Dialogs.AskYesNoAsync("Save", $"{error.Message}\n\nReplace the file on disk with this one?", "Replace", danger: true))
            {
                await SaveToAsync(doc, path, force: true);
            }
        }
        catch (ApiException error)
        {
            _error = error;
        }
    }

    // The server's answer when the file on disk is newer than the one opened.
    private const int ConflictStatus = 409;

    private Task<SavedDocument> SaveCallAsync(OpenDocument doc, string path, double? modified, bool force)
    {
        if (doc.IsNotebook && doc.NotebookView is { } view)
        {
            var (cells, next) = view.ToSave();
            return Workbench.SaveNotebookAsync(path, cells, next, modified, force);
        }
        return Workbench.SaveScriptAsync(path, doc.ScriptText, modified, force);
    }

    private Task EditorPageKeyAsync(string key) => key == "saveAs" ? SaveAsAsync(Front) : SaveAsync(Front);

    private Task InsertAsync(string line) =>
        Front?.NotebookView?.InsertAsync(line) ?? Front?.ScriptView?.InsertAsync(line) ?? Task.CompletedTask;

    /// <summary>A group's main Run: Run all for a notebook, Run file for a script (F5).</summary>
    private Task RunMainAsync(OpenDocument doc) =>
        doc.NotebookView?.RunAllAsync() ?? doc.ScriptView?.RunFileAsync() ?? Task.CompletedTask;
}
