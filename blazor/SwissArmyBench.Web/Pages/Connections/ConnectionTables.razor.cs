using Microsoft.AspNetCore.Components;
using Microsoft.JSInterop;

using SwissArmyBench.Web.Api;
using SwissArmyBench.Web.Api.Connections;
using SwissArmyBench.Web.State;

namespace SwissArmyBench.Web.Pages.Connections;

public partial class ConnectionTables
{
    /// <summary>Tables drawn at once in a group (the search finds the rest).</summary>
    private const int TablesShownAtOnce = 400;

    private readonly Dictionary<TreeTable, (TablePreview? Rows, Exception? Error)> _previews = [];
    private ConnectionTree? _tree;
    private string? _failed;
    private Exception? _error;
    private string _search = string.Empty;
    private string? _busyWords;
    private TreeTable? _reading;

    [Inject]
    private ConnectionsClient Connections { get; set; } = default!;

    [Inject]
    private Dialogs Dialogs { get; set; } = default!;

    [Inject]
    private Notes Notes { get; set; } = default!;

    [Inject]
    private NavigationManager Nav { get; set; } = default!;

    [Inject]
    private IJSRuntime Js { get; set; } = default!;

    [Parameter, EditorRequired]
    public string Name { get; set; } = string.Empty;

    private bool IsPowerBi => _tree?.Kind == "powerbi";

    private bool Single => _tree is { Groups.Count: 1 } && !IsPowerBi;

    protected override async Task OnParametersSetAsync()
    {
        _tree = null;
        _failed = null;
        try
        {
            _tree = await Connections.TreeAsync(Name);
            if (_tree.State?.State == "failed" && _tree.Groups.Count == 0)
            {
                _failed = _tree.State.Error ?? "The catalog did not load.";
            }
        }
        catch (ApiException error)
        {
            _tree = new ConnectionTree(Name, string.Empty, []);
            _failed = error.Refusal.Error;
        }
    }

    /// <summary>The groups with the tables the search finds (a group with none left goes, while searching).</summary>
    private IEnumerable<(TreeGroup Group, IReadOnlyList<TreeTable> Tables)> Shown()
    {
        var words = _search.Trim();
        return (_tree?.Groups ?? [])
            .Select(g => (g, (IReadOnlyList<TreeTable>)g.Tables
                .Where(t => words.Length == 0 || $"{g.Schema}.{t.Table}".Contains(words, StringComparison.OrdinalIgnoreCase))
                .ToList()))
            .Where(x => x.Item2.Count > 0 || words.Length == 0);
    }

    private string TitleOf(TreeGroup group) =>
        group.Schema is { Length: > 0 } schema ? schema : group.Database is { Length: > 0 } database ? database : _tree?.Connection ?? Name;

    private async Task OpenAsync(TreeTable table) => await GuardAsync("Opening…", async () =>
    {
        var got = await Connections.OpenAsync(Name, table);
        _ = Notes.SayAsync($"{got.Dataset ?? table.Table} is open on the Tables page.");
        Nav.NavigateTo("tables");
    });

    private async Task PreviewAsync(TreeTable table)
    {
        if (_previews.Remove(table))
        {
            return; // a second click folds it away
        }
        _reading = table;
        try
        {
            _previews[table] = (await Connections.PreviewAsync(Name, table) with { Table = table.Table, Schema = table.Schema }, null);
        }
        catch (ApiException error)
        {
            _previews[table] = (null, error);
        }
        _reading = null;
    }

    private async Task CopyAsync(string sql)
    {
        await Js.InvokeAsync<bool>("sab.copy", sql);
        _ = Notes.SayAsync($"Copied {sql}");
    }

    private async Task OpenAllAsync(TreeGroup group)
    {
        var schema = group.Schema ?? string.Empty;
        if (!await Dialogs.AskYesNoAsync("Open all", $"Open all {group.Count} tables of {schema}? Each opens as its own tab.", "Open all"))
        {
            return;
        }
        await GuardAsync($"Opening {group.Count} tables of {schema}…", async () =>
        {
            var got = await Connections.OpenDatasetAsync(Name, schema);
            if (got.Failed.Count > 0)
            {
                var could = $" {got.Failed.Count} could not: {string.Join(", ", got.Failed.Select(f => f.Table))}.";
                _error = new ApiException(0, new Refusal($"{got.Opened.Count} tables of {schema} are open.{could}", schema, Details: string.Join("\n", got.Failed.Select(f => $"{f.Table}: {f.Error}"))), string.Empty);
            }
            else
            {
                _ = Notes.SayAsync($"{got.Opened.Count} tables of {schema} are open.");
            }
        });
    }

    private Task ImportRelationshipsAsync(TreeGroup group) => GuardAsync($"Reading {group.Schema}'s relationships…", async () =>
    {
        var got = await Connections.RelationshipsAsync(Name, group.Schema);
        _ = Notes.SayAsync($"{got.Imported.Count} relationships from {group.Schema} are in the model.");
    });

    /// <summary>A new %%sql cell in the Notebooks page's notebook, else the cell's text on the clipboard.</summary>
    private async Task QueryInNotebookAsync(string sql)
    {
        var source = $"SELECT *\nFROM {sql}\nLIMIT 100";
        try
        {
            await Connections.QueryInNotebookAsync(source);
            Nav.NavigateTo("notebooks");
            _ = Notes.SayAsync("A SQL cell is in the notebook.");
        }
        catch (ApiException)
        {
            await Js.InvokeAsync<bool>("sab.copy", $"%%sql\n{source}");
            _ = Notes.SayAsync("Copied as a %%sql cell: paste it into a notebook.");
        }
    }

    private async Task GuardAsync(string words, Func<Task> work)
    {
        _busyWords = words;
        _error = null;
        try
        {
            await work();
        }
        catch (ApiException error)
        {
            _error = error;
        }
        _busyWords = null;
    }
}
