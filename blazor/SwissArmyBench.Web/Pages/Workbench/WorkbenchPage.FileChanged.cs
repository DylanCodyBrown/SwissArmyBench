using SwissArmyBench.Web.State;

namespace SwissArmyBench.Web.Pages.Workbench;

// A document whose file changed anywhere (the classic workbenchFileChanged.ts; services/code_files.py's file_changed
// notice): one with nothing unsaved is read again in place; one with unsaved edits, or whose file is gone, gets a bar
// over it (Reload, Keep mine; a gone file: Save as…, Close). Never silently overwritten.
public partial class WorkbenchPage
{
    private void OnFileNotice(Notice notice)
    {
        if (notice.Type != "file_changed" || notice.Text("path") is not { } path)
        {
            return;
        }
        var hash = notice.Text("hash");
        _ = InvokeAsync(async () =>
        {
            foreach (var doc in _documents.Where(d => SamePath(d.Path, path)).ToList())
            {
                await FileChangedAsync(doc, hash);
            }
            await LoadTreeAsync();
            StateHasChanged();
        });
    }

    private async Task FileChangedAsync(OpenDocument doc, string? hash)
    {
        if (hash is not null && hash == doc.Hash)
        {
            return; // this page's own save, or the same text
        }
        if (hash is not null && !doc.Dirty)
        {
            await GuardAsync(() => ReloadAsync(doc));
            return;
        }
        doc.Elsewhere = hash is null ? "gone" : "changed";
    }

    /// <summary>The document read again from its file: a script's text in place (its cursor kept), a notebook's cells
    /// as they are now (its view drawn again, the same tab and session).</summary>
    private async Task ReloadAsync(OpenDocument doc)
    {
        if (doc.Path is not { } path)
        {
            return;
        }
        if (doc.IsNotebook)
        {
            doc.Notebook = await Workbench.OpenNotebookAsync(path);
            (doc.Modified, doc.Hash) = (doc.Notebook.Modified, doc.Notebook.Hash);
            doc.Kept.Started = false;
            doc.Version++;
        }
        else
        {
            var script = await Workbench.OpenScriptAsync(path);
            (doc.ScriptText, doc.Modified, doc.Hash) = (script.Text, script.Modified, script.Hash);
        }
        (doc.Dirty, doc.Elsewhere) = (false, null);
    }

    /// <summary>Keep mine: this page's text stays, and its Save writes over the file as it is now.</summary>
    private async Task KeepMineAsync(OpenDocument doc)
    {
        if (doc.Path is not { } path)
        {
            return;
        }
        if (doc.IsNotebook)
        {
            var found = await Workbench.OpenNotebookAsync(path);
            (doc.Modified, doc.Hash) = (found.Modified, found.Hash);
        }
        else
        {
            var found = await Workbench.OpenScriptAsync(path);
            (doc.Modified, doc.Hash) = (found.Modified, found.Hash);
        }
        doc.Elsewhere = null;
    }
}
