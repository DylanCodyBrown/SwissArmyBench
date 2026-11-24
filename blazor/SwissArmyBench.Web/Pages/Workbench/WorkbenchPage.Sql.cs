using Microsoft.AspNetCore.Components;
using Microsoft.JSInterop;

using SwissArmyBench.Web.Api;
using SwissArmyBench.Web.Api.Grids;
using SwissArmyBench.Web.Api.Workbench;
using SwissArmyBench.Web.State;

namespace SwissArmyBench.Web.Pages.Workbench;

// A SQL file's bar and its run's end (the owner, 2026-11-24: "should be able to select a connection in a drop down
// beside the run file button" / "then when you run the file, it adds the table and opens the grid back on the grid
// menu"): the dropdown (Open tables (DuckDB) first, then each connection that runs SQL, in its colour) writes the
// file's `-- connection:` line; a run's table brought forward on the Tables page.
public partial class WorkbenchPage
{
    // The app's first window, where the Tables page is (shell.js names it).
    private const string HomeWindow = "sab-home";

    // The Tables page in a window of its own, when the home window holds unsaved documents.
    private const string TablesWindow = "sab-tables";

    private IReadOnlyList<string> _sqlConnections = [];

    [Inject]
    private ApiClient Api { get; set; } = default!;

    [Inject]
    private ConnectionColours Colours { get; set; } = default!;

    private async Task LoadSqlConnectionsAsync()
    {
        try
        {
            _sqlConnections = (await Api.GetAsync<ConnectionsListing>("/connections")).Connections
                .Where(c => c.RunsSql)
                .Select(c => c.Name)
                .OrderBy(n => n, StringComparer.OrdinalIgnoreCase)
                .ToList();
            await Colours.LoadAsync();
        }
        catch (ApiException)
        {
            _sqlConnections = []; // the open tables still run
        }
    }

    /// <summary>A run built its table: said, and the Tables page brought forward on it.</summary>
    private async Task SqlBuiltAsync(SqlRun built)
    {
        await Notes.SayAsync($"Built {built.Table}: {SqlFileView.Rows(built.Rows)}{(built.Connection is { } on ? $" from {on}" : string.Empty)}.");
        await ShowTableAsync(built.Grid);
    }

    /// <summary>The table's tab on the Tables page: the home window brought forward on it. When this page is the home
    /// window it goes there, unless a document here has unsaved changes: then the Tables page opens in a window of its
    /// own (or, where the browser blocks it, a note offers it), so nothing typed here is lost.</summary>
    private async Task ShowTableAsync(string grid)
    {
        var address = $"tables?grid={Uri.EscapeDataString(grid)}";
        var here = await Js.InvokeAsync<string>("sab.windowName");
        if (here != HomeWindow && await Js.InvokeAsync<bool>("sab.openWindow", address, HomeWindow, string.Empty))
        {
            return;
        }
        if (_documents.Any(d => d.Dirty))
        {
            if (await Js.InvokeAsync<bool>("sab.openWindow", address, TablesWindow, string.Empty))
            {
                return;
            }
            await Notes.SayAsync("The table is open on the Tables page.", "Show", () =>
            {
                Nav.NavigateTo(address);
                return Task.CompletedTask;
            });
            return;
        }
        Nav.NavigateTo(address);
    }
}
