using System.Text.Json;

using SwissArmyBench.Web.State;

namespace SwissArmyBench.Web.Pages.Workbench;

// The page's own answers to the agent's workbench_window commands that take arguments or give something back (the
// classic workbenchCommands.ts): what is open, a file opened at a line or a cell, the project's unsaved documents
// saved, where the Data Explorer's Insert goes. Every other command is the palette's (State/Commands.AnswerAsync).
public partial class WorkbenchPage
{
    private async Task<CommandAnswer?> AgentAnswerAsync(string command, JsonElement args)
    {
        switch (command)
        {
            case State.Commands.PlaceCommand:
                return At(null);
            case "documents":
                return At(new { page = Page, documents = _documents.Select(DocumentFacts).ToList() });
            case "explorer.target":
                return At(new { document = Front?.Path, title = Front?.Title, cell = Front?.NotebookView?.Selected?.Number });
            case "file.openAt":
            case "file.openCell":
                return await OpenAtAsync(args);
            case "project.saveDocuments":
                return await SaveDocumentsAsync(args);
            case "file.new" or "file.newSql" or "tabs.new-query" or "workbook.new":
                return await AgentNewFileAsync(command, args);
            case "view.preview" or "view.split" or "view.source" or "preview.saveSvg" or "preview.savePng":
                return await TextAnswerAsync(command, args);
            default:
                return await ReviewAnswerAsync(command, args);
        }
    }

    // The agent's file.new {"name", "type"?, "folder"?} (file.newSql: a SQL file; workbook.new: a workbook's
    // design): the file named and written by the server, then its tab, as the dialog's Create does. The dialog
    // itself is the user's (it opens on their screen): with no name the agent is told to pass one.
    private async Task<CommandAnswer?> AgentNewFileAsync(string command, JsonElement args)
    {
        if (TextOf(args, "name") is not { Length: > 0 } name)
        {
            throw new InvalidOperationException("Give the file a name (args.name): a new file is made only once it is named. workbench_file new makes one the same way.");
        }
        var type = TextOf(args, "type") ?? command switch
        {
            "file.newSql" => "sql",
            "workbook.new" => "workbook",
            _ => IsNotebooks ? "notebook" : "python",
        };
        var made = await ScriptIde.NewFileAsync(new Api.Workbench.NewFileRequest(type, name, TextOf(args, "folder") ?? await NewFileFolderAsync(type)));
        await NewFileMadeAsync(made);
        return new CommandAnswer(new { ran = command, path = made.Path, relative = made.Relative }, made.Path, FilePaths.Name(made.Path), null);
    }

    private CommandAnswer At(object? result) => new(result, Front?.Path, Front?.Title, Front?.NotebookView?.Selected?.Number);

    private object DocumentFacts(OpenDocument doc, int index) => new
    {
        index,
        title = doc.Title,
        path = doc.Path,
        kind = doc.IsCode ? (doc.IsNotebook ? "notebook" : "script") : doc.KindWord,
        unsaved_changes = doc.Dirty,
        front = doc == Front,
    };

    // {"path", "line"} or {"path", "cell"}: the file's tab, its line or cell in view (the page's own address).
    private async Task<CommandAnswer?> OpenAtAsync(JsonElement args)
    {
        if (TextOf(args, "path") is not { Length: > 0 } path)
        {
            throw new InvalidOperationException("path is the file to open.");
        }
        var page = path.EndsWith(".ipynb", StringComparison.OrdinalIgnoreCase) ? "notebooks" : "scripts";
        var at = NumberOf(args, "cell") is { } cell ? $"&cell={cell}" : NumberOf(args, "line") is { } line ? $"&line={line}" : string.Empty;
        Nav.NavigateTo($"{page}?path={Uri.EscapeDataString(path)}{at}");
        await Task.Yield();
        return new CommandAnswer(new { opened = path }, path, FilePaths.Name(path), NumberOf(args, "cell"));
    }

    // {"folder"}: the documents under it with unsaved changes, saved as they stand here (the project's Save).
    private async Task<CommandAnswer?> SaveDocumentsAsync(JsonElement args)
    {
        var folder = (TextOf(args, "folder") ?? string.Empty).Replace('\\', '/').TrimEnd('/');
        var unsaved = _documents
            .Where(d => d.Dirty && d.Path is { } path && (folder.Length == 0 || path.Replace('\\', '/').StartsWith(folder + "/", StringComparison.OrdinalIgnoreCase)))
            .ToList();
        foreach (var doc in unsaved)
        {
            await SaveAsync(doc);
        }
        return At(new { saved = unsaved.Select(d => d.Path).ToList() });
    }

    private static string? TextOf(JsonElement args, string name) =>
        args.ValueKind == JsonValueKind.Object && args.TryGetProperty(name, out var value) && value.ValueKind == JsonValueKind.String ? value.GetString() : null;

    private static int? NumberOf(JsonElement args, string name) =>
        args.ValueKind == JsonValueKind.Object && args.TryGetProperty(name, out var value) && value.TryGetInt32(out var number) ? number : null;
}
