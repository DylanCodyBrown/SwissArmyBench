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
        if (path.EndsWith(".design.json", StringComparison.OrdinalIgnoreCase))
        {
            // A workbook's design opens as a tab of the Notebooks page (whatever the mode: the classic's own rule).
            if (IsNotebooks)
            {
                OpenWorkbook(path);
            }
            else
            {
                _wrongPage = ($"{FilePaths.Name(path)} is a workbook: it opens on the Notebooks page.", $"notebooks?path={Uri.EscapeDataString(path)}");
            }
            return;
        }
        if (StructureFiles.IsStructure(path))
        {
            OpenStructure(path, null);
            return;
        }
        var notebook = path.EndsWith(".ipynb", StringComparison.OrdinalIgnoreCase);
        if (notebook != IsNotebooks)
        {
            // A file opens on its kind's page (the classic workbench_pages.py's one line).
            var page = notebook ? "notebooks" : "scripts";
            _wrongPage = ($"{FilePaths.Name(path)} is a {(notebook ? "notebook" : "script")}: it opens on the {(notebook ? "Notebooks" : "Scripts")} page.", $"{page}?path={Uri.EscapeDataString(path)}");
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
                (doc.Path, doc.Modified, doc.Hash) = (doc.Notebook.Path, doc.Notebook.Modified, doc.Notebook.Hash);
            }
            else
            {
                var script = await Workbench.OpenScriptAsync(path);
                (doc.Path, doc.Modified, doc.ScriptText, doc.Hash) = (script.Path, script.Modified, script.Text, script.Hash);
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

    private int NextUntitled(bool sql = false) =>
        _documents.Where(d => d.Path is null && d.NewSql == sql).Select(d => d.Untitled).DefaultIfEmpty(0).Max() + 1;

    // A new SQL file's first text: a SELECT to finish (the dropdown beside Run file says where it runs).
    private const string SqlStarter = "SELECT *\nFROM ";

    private OpenDocument NewSqlDocument() => new(++_nextKey, false) { Untitled = NextUntitled(sql: true), NewSql = true, ScriptText = SqlStarter };

    /// <summary>New ▸ SQL file: an untitled .sql tab on the Scripts page (DuckDB over the open tables until a
    /// connection is chosen beside Run file).</summary>
    private Task NewSqlAsync()
    {
        AddDocument(NewSqlDocument());
        return FollowAddressAsync();
    }

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
        var fresh = BladeAddress is null && CodeFileAddress is null && path is null && Front is not null;
        var freshKind = Front is { NewSql: true } ? "sql" : "1";
        // The address this writes is the page's own: read back, it must not open or make anything again (a
        // shown untitled script's ?new=1 made another one on every click: the owner, 2026-11-23).
        _shownFor = AddressKey(BladeAddress is null && CodeFileAddress is null ? path : null, fresh ? freshKind : string.Empty, Front?.Blade, null, null, Front?.CodeFile);
        Nav.NavigateTo(BladeAddress ?? CodeFileAddress ?? (path is null ? (Front is null ? Page : $"{Page}?new={freshKind}") : $"{Page}?path={Uri.EscapeDataString(path)}"), replace: true);
        await Js.InvokeVoidAsync("sab.setTitle", Title);
    }

    /// <summary>A tab closed; one with unsaved changes is asked about first.</summary>
    private async Task CloseAsync(int key) => await CloseAsync(key, force: false);

    private async Task CloseAsync(int key, bool force)
    {
        if (!_byKey.TryGetValue(key, out var doc))
        {
            return;
        }
        if (!force && doc.Dirty && !await Dialogs.AskYesNoAsync("Close", $"{doc.Title} has changes that are not saved. Close it anyway?", "Close", danger: true))
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
        if (Front is { BladeIde: { } blade })
        {
            await blade.SaveAsync();
        }
        else if (Front is { } doc)
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

    private Task SaveAsync(OpenDocument? doc) => doc is { CodeFileView: { } codeFile } ? SaveCodeFileAsync(doc, codeFile)
        : doc is { WorkbookView: { } workbook } ? workbook.SaveAsync()
        : doc is { StructureDoc: { } structure } ? structure.SaveAsync()
        : doc is null ? Task.CompletedTask : doc.Path is null ? SaveAsAsync(doc) : SaveToAsync(doc, doc.Path);

    private async Task SaveAsAsync(OpenDocument? doc)
    {
        if (doc is { WorkbookView: { } workbook })
        {
            await workbook.SaveAsync(asNew: true);
            return;
        }
        if (doc is { StructureDoc: { } structure })
        {
            await structure.SaveAsAsync();
            return;
        }
        if (doc is null)
        {
            return;
        }
        var home = await Workbench.HomeAsync();
        var start = doc.Path is null ? home.Folder : FilePaths.Folder(doc.Path);
        if (await Files.ChooseAsync("save", "Save as", start, Kind, name: doc.Path is null ? SuggestedName(doc) : null) is not { } chosen)
        {
            return;
        }
        await SaveToAsync(doc, WithEnding(doc, chosen));
    }

    private async Task SaveToAsync(OpenDocument doc, string path, bool force = false)
    {
        try
        {
            var renamed = path != doc.Path;
            var saved = await SaveCallAsync(doc, path, renamed ? null : doc.Modified, force);
            (doc.Path, doc.Modified, doc.Dirty, doc.Hash, doc.Elsewhere) = (saved.Path, saved.Modified, false, saved.Hash, null);
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
            return Workbench.SaveNotebookAsync(path, cells, next, modified, force, doc.IsData ? doc.Descriptions ?? doc.Notebook?.Dictionary : null);
        }
        return Workbench.SaveScriptAsync(path, doc.ScriptText, modified, force);
    }

    private Task EditorPageKeyAsync(string key) => key == "saveAs" ? SaveAsAsync(Front) : SaveAsync(Front);

    private Task InsertAsync(string line) =>
        Front?.NotebookView?.InsertAsync(line) ?? Front?.ScriptView?.InsertAsync(line) ?? Front?.SqlView?.InsertAsync(line) ?? Task.CompletedTask;

    /// <summary>A group's main Run: Run all for a notebook, Run file for a script (F5).</summary>
    private Task RunMainAsync(OpenDocument doc) => IsApiFile(doc) ? RunApiAsync(doc)
        : doc.NotebookView?.RunAllAsync() ?? doc.SqlView?.RunFileAsync() ?? doc.ScriptView?.RunFileAsync() ?? Task.CompletedTask;

    /// <summary>API.py, the project's local sandbox API: its main Run is Run API.</summary>
    private static bool IsApiFile(OpenDocument doc) =>
        !doc.IsNotebook && doc.IsCode && doc.Path is { } path && (path.EndsWith("/API.py", StringComparison.Ordinal) || path.EndsWith("\\API.py", StringComparison.Ordinal) || path == "API.py");

    /// <summary>Run API: saved first, then hosted as the APIs page's Run hosts it; another project's API.py runs as a plain file.</summary>
    private Task RunApiAsync(OpenDocument doc) => GuardAsync(async () =>
    {
        if (doc.Dirty)
        {
            await SaveAsync(doc);
        }
        var now = await Workbench.LocalApiAsync();
        if (now.File is null || !SamePath(now.File, doc.Path))
        {
            await (doc.ScriptView?.RunFileAsync() ?? Task.CompletedTask);
            return;
        }
        var done = await Workbench.RunLocalApiAsync();
        if (done.Failed is { } failed)
        {
            if (failed.Line is { } line)
            {
                await (doc.ScriptView?.RevealLineAsync(line) ?? Task.CompletedTask);
            }
            throw new InvalidOperationException(failed.Line is { } at ? $"{failed.Error} (API.py line {at})" : failed.Error);
        }
        if (done.Running is { } running)
        {
            await Notes.SayAsync($"Running on {running.Url} · {running.Endpoints} {(running.Endpoints == 1 ? "endpoint" : "endpoints")}");
        }
    });
}
