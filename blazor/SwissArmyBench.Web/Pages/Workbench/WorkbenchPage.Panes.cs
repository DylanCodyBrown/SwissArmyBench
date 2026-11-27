using System.Text.RegularExpressions;

using Microsoft.AspNetCore.Components.Web;
using Microsoft.JSInterop;

using SwissArmyBench.Web.Api;
using SwissArmyBench.Web.Api.Catalog;
using SwissArmyBench.Web.Api.Connections;
using SwissArmyBench.Web.Components;
using SwissArmyBench.Web.State;

namespace SwissArmyBench.Web.Pages.Workbench;

// The page's panes and getting between them (the classic workbenchLayout.ts and workbenchExplorer.ts): the Data
// Explorer on the left (Ctrl+Shift+E; its Table menu, Insert and Open, Pop out), the console shown or hidden, F6 and
// Shift+F6 from pane to pane, Ctrl+1 back to the source; and the palette's View and Data commands for them.
public partial class WorkbenchPage
{
    private bool _showExplorer;
    private ExplorerPane? _explorer;

    [GeneratedRegex(@"[^A-Za-z0-9_]+")]
    private static partial Regex NotNamePart();

    private async Task ToggleExplorerAsync()
    {
        _showExplorer = !_showExplorer;
        await Js.InvokeVoidAsync("sab.remember", $"{Page}.explorer", _showExplorer ? "1" : "0");
    }

    private async Task CyclePaneAsync(int by)
    {
        if (_module is not null)
        {
            await _module.InvokeVoidAsync("cyclePane", by);
        }
    }

    private Task FocusSourceAsync() => Js.InvokeVoidAsync("sab.focus", ".wb-group.focused .monaco-editor textarea").AsTask();

    private Task ToggleConsoleAsync()
    {
        Front?.ScriptView?.ToggleConsole();
        return Task.CompletedTask;
    }

    /// <summary>Add a table (the Data Explorer's Table, the palette): a file, a loaded catalog's, a connection or an API.</summary>
    private Task AddTableMenuAsync(MouseEventArgs at)
    {
        List<MenuEntry> entries =
        [
            new("Open file…", "file", OpenFileAsTableAsync),
            .. _connections.Select(name => new MenuEntry(name, "data", () => Go($"connections?name={Uri.EscapeDataString(name)}"))),
            new("Search the catalog…", "zoom", () => Go("catalog")),
            MenuEntry.Separator,
            new("Add connection…", "plug", () => Go("connections?add=1")),
            new("Add API…", "apis", () => Go("apis")),
        ];
        _menu = new ShownMenu("Add a table", entries, at.ClientX, at.ClientY + 4);
        return Task.CompletedTask;
    }

    /// <summary>Open a file as a table: its name from the file's, read into the grids.</summary>
    private async Task OpenFileAsTableAsync()
    {
        var home = await Workbench.HomeAsync();
        if (await Files.ChooseAsync("file", "Open a file as a table", home.Folder, "data") is not { } path)
        {
            return;
        }
        var stem = FilePaths.Stem(path);
        var name = NotNamePart().Replace(stem, "_").Trim('_') is { Length: > 0 } plain ? plain : "table";
        await GuardAsync(async () =>
        {
            await Workbench.LoadFileAsync(name, path);
            await Notes.SayAsync($"{name} is open on the Tables page.");
        });
    }

    /// <summary>A Data Explorer result's code where the cursor is: a SQL cell's SQL, else its Python.</summary>
    private Task InsertExplorerAsync(InsertText insert)
    {
        var sql = Front?.NotebookView?.Selected?.Kind is "sql";
        var text = sql && insert.Sql.Length > 0 ? insert.Sql : insert.Python.Length > 0 ? insert.Python : insert.Sql;
        return InsertAsync(text);
    }

    private async Task OpenExplorerResultAsync(SearchResult result)
    {
        if (result.Grid is { } grid)
        {
            Nav.NavigateTo($"tables?grid={Uri.EscapeDataString(grid)}");
            return;
        }
        if (result.Connection is { } connection && result.Place is { } place)
        {
            await GuardAsync(async () =>
            {
                await ConnectionsApi.OpenAsync(connection, new TreeTable(place.Table, place.Database, place.Schema));
                await Notes.SayAsync($"{place.Table} is open on the Tables page.");
            });
        }
    }

    private async Task OpenAtFileAsync(string path)
    {
        await OpenPathAsync(path);
        await FollowAddressAsync();
    }

    private Task PopExplorerAsync() => Js.InvokeVoidAsync("open", "catalog", "_blank").AsTask();

    /// <summary>The project's files at the Data Explorer's foot (its tree's notebooks and scripts).</summary>
    private IReadOnlyList<string> ExplorerFiles =>
        (_tree?.Groups ?? []).SelectMany(g => g.Files).Select(f => f.Full ?? f.Path).Distinct().Take(40).ToList();

    private string ExplorerTarget => Front is null ? "Nothing: open a notebook or a script"
        : Front.NotebookView?.Selected is { } cell ? $"{Front.Title}, cell {cell.Number}" : Front.Title;

    private List<PaletteCommand> PaneCommands() =>
    [
        new("view.explorer", "View", "Show or hide the Data Explorer", ToggleExplorerAsync, "Ctrl+Shift+E"),
        new("view.toggleConsole", "View", "Show or hide the console", ToggleConsoleAsync, WhyNot: Front?.ScriptView is null ? "A script's console: put a script in front" : null),
        new("view.source", "View", "Go to the source", FocusSourceAsync, "Ctrl+1"),
        new("view.nextPane", "View", "Next pane", () => CyclePaneAsync(1), "F6"),
        new("view.previousPane", "View", "Previous pane", () => CyclePaneAsync(-1), "Shift+F6"),
        new("explorer.search", "Data", "Search the Data Explorer (it opens): its results as data", SearchExplorerAsync),
        new("explorer.target", "Data", "Where the Data Explorer's Insert goes: the focused document and its cell", () => ShowHelp("Where Insert goes", ExplorerTarget)),
        new("explorer.popOut", "Data", "Pop the Data Explorer out: the Catalog page in a window of its own, with its search", PopExplorerAsync),
        new("data.openFile", "Data", "Open a file as a table…", OpenFileAsTableAsync),
        new("data.tables", "Data", "The open tables and the blades' variables (the Data Explorer's)", OpenTablesAsync),
        new("tables.transformations", "Tables", "Show a table's transformations (its read-only cell, wherever it lives)", () => Go("environment?at=tables")),
    ];

    private async Task SearchExplorerAsync()
    {
        if (await Dialogs.AskTextAsync("Search the Data Explorer", "Tables, columns, connections, structures, APIs, variables, blades.", "Search", string.Empty, "Search") is not { } text)
        {
            return;
        }
        _showExplorer = true;
        StateHasChanged();
        await Task.Yield();
        if (_explorer is not null)
        {
            await _explorer.SearchAsync(text);
        }
    }

    private async Task OpenTablesAsync()
    {
        try
        {
            var tables = (await Workbench.TablesAsync()).Tables;
            await ShowHelp("The open tables", string.Join('\n', tables.Select(t => $"{t.Name}: {t.Rows:N0} rows · {t.Origin}")));
        }
        catch (ApiException error)
        {
            _error = error;
        }
    }
}
