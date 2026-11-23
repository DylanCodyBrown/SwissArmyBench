using System.Text;
using System.Text.RegularExpressions;

using Microsoft.JSInterop;

using SwissArmyBench.Web.Api.Workbench;

namespace SwissArmyBench.Web.Pages.Workbench;

// What the page exports (the classic workbenchExport.ts and projectFile.ts): data.py from data.ipynb, a document as
// one self-contained automation, the project copied to another folder, and its outline (ARCHITECTURE.md).
public partial class WorkbenchPage
{
    private async Task ExportDataAsync()
    {
        var data = _documents.FirstOrDefault(d => d.Path is not null && FilePaths.Name(d.Path) == "data.ipynb");
        var folder = data?.Path is { } path ? FilePaths.Folder(path) : Project.Current?.Path;
        if (folder is null)
        {
            throw new InvalidOperationException("No project is open (a folder with a data.ipynb).");
        }
        var done = await Exports.ExportDataAsync(folder);
        foreach (var said in done.Skipped)
        {
            await Notes.SayAsync(said);
        }
        if (done.FillIn.Count > 0)
        {
            throw new InvalidOperationException($"data.py cannot read {string.Join(", ", done.FillIn)} again: add the code that reads it to data.ipynb.");
        }
    }

    private async Task CopyProjectAsync()
    {
        if (Project.Current is not { } project)
        {
            return;
        }
        var name = FilePaths.Name(project.Path);
        if (await Files.ChooseAsync("save", $"Copy {name} to", FilePaths.Folder(project.Path), "project") is not { } target)
        {
            return;
        }
        var rows = await Dialogs.AskYesNoAsync("Copy its rows too?", "Copy the rows kept in .sab/data too?\n\nData is sensitive: without them, only the project's own files are copied.", "With the rows");
        var done = await Exports.CopyProjectAsync(target, rows);
        await Notes.SayAsync($"Copied to {done.Copied}");
    }

    /// <summary>ARCHITECTURE.md written at the project's top (only when its bytes change), then downloaded.</summary>
    private async Task ExportOutlineAsync()
    {
        var done = await Exports.OutlineAsync();
        await Notes.SayAsync($"{done.File} {(done.Written ? "written" : "is up to date")}");
        var data = $"data:text/markdown;base64,{Convert.ToBase64String(Encoding.UTF8.GetBytes(done.Text))}";
        await Js.InvokeVoidAsync("sab.download", data);
    }

    /// <summary>Export as one Python script… or as one notebook…: the document as it stands here, as one file that
    /// runs with plain python (or top to bottom in any Jupyter). A connection that runs only here is said first; what
    /// cannot be exported is named, and the rest goes with a FILL IN stub each only on the user's word.</summary>
    private async Task ExportDocumentAsync(OpenDocument doc, string format)
    {
        var ending = format == "notebook" ? ".ipynb" : ".py";
        var stem = Regex.Replace(FilePaths.Stem(doc.Title).Trim(), @"\W+", "_").Trim('_').ToLowerInvariant();
        var suggested = $"{(stem.Length == 0 ? "job" : stem)}_automation{ending}";
        var start = doc.Path is null ? (await Workbench.HomeAsync()).Folder : FilePaths.Folder(doc.Path);
        var title = format == "notebook" ? "Export as one notebook" : "Export as one Python script";
        if (await Files.ChooseAsync("save", title, start, "file", name: suggested) is not { } path)
        {
            return;
        }
        path = path.EndsWith(ending, StringComparison.OrdinalIgnoreCase) ? path : path + ending;
        var body = new Dictionary<string, object?> { ["format"] = format, ["to"] = path, ["path"] = doc.Path, ["name"] = doc.Title };
        if (doc.NotebookView is { } view)
        {
            (body["kind"], body["cells"]) = ("notebook", view.ToSave().Cells);
        }
        else
        {
            (body["kind"], body["text"]) = ("script", doc.ScriptText);
        }
        var looked = await Exports.ExportScriptAsync(body, check: true);
        if (looked.LocalWords is { } local && !await Dialogs.AskYesNoAsync(title, $"{local}\n\nExport it anyway?", "Export"))
        {
            await Notes.SayAsync("Nothing was exported.");
            return;
        }
        var done = await Exports.ExportScriptAsync(body);
        if (done.Ask is not null)
        {
            var said = string.Join("\n", done.Problems.Concat(done.Lint).Select(p => $"• {p}"));
            if (!await Dialogs.AskYesNoAsync(title, $"These cannot be exported:\n{said}\n\nExport the rest, with a stub that raises FILL IN for each?", "Export the rest"))
            {
                await Notes.SayAsync("Nothing was exported.");
                return;
            }
            done = await Exports.ExportScriptAsync(body, stub: true);
        }
        await SayExportedAsync(done);
    }

    private async Task SayExportedAsync(ScriptExport done)
    {
        foreach (var said in done.Skipped)
        {
            await Notes.SayAsync(said);
        }
        var secrets = done.Settings.Where(s => s.Secret).Select(s => s.Variable).ToList();
        var note = secrets.Count > 0 ? $" Set {string.Join(", ", secrets)} where it runs." : string.Empty;
        var stubs = done.Stubs.Count > 0 ? $" (FILL IN: {string.Join(", ", done.Stubs)})" : string.Empty;
        await Notes.SayAsync($"Exported {done.File}{stubs}.{note}");
    }
}
