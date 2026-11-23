using SwissArmyBench.Web.Api;

namespace SwissArmyBench.Web.Pages.Workbench;

// The palette's commands for a document's cells, tables and help (the classic workbenchCommandList.ts): open a
// document at a cell, select or edit a cell, a cell's lineage, the run order, the Tables group's (list, add, run,
// fold, open, a table's transformations, go to its cell), the HTML cells' (list, run, size, open its HTML), reopen
// the last closed table, and help on the name at the cursor (F1: a card beside the code).
public partial class WorkbenchPage
{
    private const string NoCode = "No notebook or script is in front";

    private string? _helpCard;

    private List<WorkbenchCommand> PaletteCommands()
    {
        var code = Front is { IsBlade: false, IsStructure: false } ? null : NoCode;
        var notebook = Front?.NotebookView;
        var noNotebook = notebook is null ? "The document in front is not a notebook" : null;
        return
        [
            new("file.openCell", "File", "Open a document at a cell (a connection's reference)", OpenAtCellAsync),
            new("cell.select", "Cell", "Select a cell", () => notebook!.GoToCellAsync(), Disabled: noNotebook),
            new("cell.edit", "Cell", "Edit the cell (an HTML or Markdown cell that shows as drawn)", () => notebook!.EditSelectedAsync(), "Enter", noNotebook),
            new("lineage.open", "Cell", "Lineage: the cell back to the data, with its values", LineageOfFrontAsync, Disabled: code ?? (notebook?.Selected is null && Front?.ScriptView is null ? NoCell : null)),
            new("notebook.runOrder", "Notebook", "The run order: each cell's makes, reads and state (notRun, edited, outOfDate)",
                () => ShowHelp("The run order", notebook?.RunOrderText() ?? string.Empty), Disabled: noNotebook),
            new("tables.list", "Tables", "The document's tables and each cell's state",
                () => ShowHelp("The document's tables", string.Join('\n', notebook?.TablesShown().Select(t => $"{t.Table}: cell {t.Cell}") ?? [])), Disabled: noNotebook),
            new("tables.run", "Tables", "Run a table's cell", () => AskTableAsync("Run a table's cell", t => notebook!.RunTableNamedAsync(t)), Disabled: noNotebook),
            new("tables.runOutOfDate", "Tables", "Run every table's cell that is not up to date", () => notebook!.RunTablesAsync(), Disabled: noNotebook),
            new("tables.fold", "Tables", "Fold the Tables group (or one table)", () => Toggle(() => notebook!.FoldTables(true)), Disabled: noNotebook),
            new("tables.unfold", "Tables", "Open the Tables group (or one table)", () => Toggle(() => notebook!.FoldTables(false)), Disabled: noNotebook),
            new("data.goToTable", "Data", "Go to a table's cell in the focused document", () => AskTableAsync("Go to a table's cell", t => GoToTableAsync(t)), Disabled: noNotebook),
            new("html.list", "HTML", "The document's HTML cells (and Markdown cells with names): each one's text, names and state",
                () => ShowHelp("The HTML cells", string.Join("\n\n", notebook?.HtmlCells().Select(c => $"# [{c.Number}]\n{c.Source}") ?? [])), Disabled: noNotebook),
            new("html.run", "HTML", "Run an HTML cell (or a Markdown cell with names): fill its names", () => notebook!.RunHtmlCellsAsync(), Disabled: noNotebook),
            new("html.resize", "HTML", "Size an HTML cell's pane", ResizeHtmlAsync, Disabled: noNotebook),
            new("html.edit", "HTML", "Open an HTML cell's HTML", () => notebook!.EditSelectedAsync(), Disabled: noNotebook),
            new("tables.add", "Tables", "Add a table open in Grids to the document in front (its read-only cell)", () => AskTableAsync("Add a table", AddTableAsync), Disabled: noNotebook),
            new("doc.repoint", "Documents", "Point an open document's cells at another connection (unsaved until Save)", RepointAsync, Disabled: noNotebook),
            new("explorer.insert", "Data", "Insert a Data Explorer result's code into the focused document", InsertFoundAsync, Disabled: code),
            new("tabs.reopen", "Tabs", "Reopen the last closed table (in the home window)", ReopenTableAsync),
            new("help.atCursor", "Help", "Help on the name at the cursor", HelpAtCursorAsync, "F1", code),
        ];
    }

    private async Task OpenAtCellAsync()
    {
        if (await Dialogs.AskTextAsync("Open a document at a cell", "The file's path.", "Path", Front?.Path ?? string.Empty, "Next") is not { Length: > 0 } path)
        {
            return;
        }
        var number = await Dialogs.AskTextAsync("Open a document at a cell", "The cell's own number (none: the document).", "Cell", string.Empty, "Open");
        await OpenPathAsync(path.Trim());
        if (int.TryParse(number, out var cell) && _documents.FirstOrDefault(d => SamePath(d.Path, path.Trim())) is { } doc)
        {
            if (doc.IsNotebook)
            {
                _cellAfter = (doc.Key, cell);
            }
            else if (ScriptCells.LineOf(doc.ScriptText, cell) is { } line)
            {
                _revealAfter = (doc.Key, line);
            }
        }
        await FollowAddressAsync();
    }

    private async Task AskTableAsync(string title, Func<string, Task> then)
    {
        if (await Dialogs.AskTextAsync(title, "The table's name.", "Table", string.Empty, "Go") is { Length: > 0 } table)
        {
            await then(table.Trim());
        }
    }

    private async Task AddTableAsync(string table)
    {
        if (Front?.NotebookView is { } notebook && !await notebook.AddTableAsync(table))
        {
            await Notes.SayAsync($"{table} is not open in Grids.");
        }
    }

    private async Task RepointAsync()
    {
        if (Front?.NotebookView is not { } notebook
            || await Dialogs.AskTextAsync("Point the cells at another connection", "The connection the cells name now.", "From", string.Empty, "Next") is not { Length: > 0 } from
            || await Dialogs.AskTextAsync("Point the cells at another connection", $"The connection to name instead of {from}.", "To", string.Empty, "Point") is not { Length: > 0 } to)
        {
            return;
        }
        var changed = await notebook.RepointAsync(from.Trim(), to.Trim());
        await Notes.SayAsync(changed == 0 ? $"No cell names {from}." : $"{changed} cell{(changed == 1 ? string.Empty : "s")} now name {to}: unsaved until Save.");
    }

    /// <summary>explorer.insert: the Data Explorer's first result for the words, its code where the cursor is.</summary>
    private async Task InsertFoundAsync()
    {
        if (await Dialogs.AskTextAsync("Insert from the Data Explorer", "What to find (a table, a column, a connection…).", "Search", string.Empty, "Insert") is not { Length: > 0 } text)
        {
            return;
        }
        _showExplorer = true;
        StateHasChanged();
        await Task.Yield();
        if (_explorer is not null && (await _explorer.SearchAsync(text)).FirstOrDefault(r => r.Insert is not null) is { Insert: { } insert })
        {
            await InsertExplorerAsync(insert);
        }
        else
        {
            await Notes.SayAsync($"Nothing found for {text}.");
        }
    }

    private async Task GoToTableAsync(string table)
    {
        if (Front?.NotebookView is { } notebook && !await notebook.GoToTableAsync(table))
        {
            await Notes.SayAsync($"{table} has no cell in {Front.Title}");
        }
    }

    private async Task ResizeHtmlAsync()
    {
        if (Front?.NotebookView is not { } notebook)
        {
            return;
        }
        if (await Dialogs.AskTextAsync("Size an HTML cell's pane", "Its height in pixels (60 to 2000; empty: the design's own height).", "Height", string.Empty, "Size") is { } typed)
        {
            notebook.ResizeSelectedHtml(int.TryParse(typed, out var px) ? Math.Clamp(px, 60, 2000) : null);
        }
    }

    private async Task ReopenTableAsync()
    {
        try
        {
            await Workbench.ReopenTableAsync();
            Nav.NavigateTo("grids");
        }
        catch (ApiException error) when (error.Status == 404)
        {
            await Notes.SayAsync("No closed table to reopen.");
        }
    }

    private async Task HelpAtCursorAsync()
    {
        var help = Front?.NotebookView is { } notebook ? await notebook.HelpAsync() : Front?.ScriptView is { } script ? await script.HelpAsync() : null;
        _helpCard = help is { Length: > 0 } ? help : "No help for the name at the cursor.";
    }
}
