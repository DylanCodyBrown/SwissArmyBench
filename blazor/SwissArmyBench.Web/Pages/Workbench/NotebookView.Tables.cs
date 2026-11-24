using SwissArmyBench.Web.Api;
using SwissArmyBench.Web.Api.Workbench;
using SwissArmyBench.Web.State;

namespace SwissArmyBench.Web.Pages.Workbench;

/// <summary>
/// The notebook's Tables group (the classic workbenchTables.ts): each open table this document holds gets its
/// read-only cell, its transformations as one DuckDB query, placed by the server's rules
/// (POST /workbench/tables/arrange). A document holds a table its own code made; a project's data.ipynb holds the
/// tables no document made.
/// </summary>
public partial class NotebookView
{
    private const int ArrangeSettlesMs = 400;

    private int _arrangeAsked;

    // Tables added to this document from Grids (the palette's tables.add): their read-only cells join its group.
    private readonly HashSet<string> _added = [];

    // Counts the changes to the cells' list (added, moved, deleted): an arrange asked before one is asked again.
    private int _shape;

    private bool IsData => Path is { } path && path.Replace('\\', '/').EndsWith("/data.ipynb", StringComparison.OrdinalIgnoreCase);

    private async Task ArrangeTablesAsync()
    {
        try
        {
            var open = (await Workbench.TablesAsync()).Tables;
            var mine = open
                .Where(t => t.Document == Path || (IsData && t.Document is null) || _added.Contains(t.Name) || _kept.Cells.Any(c => c.IsAppCell && c.Table == t.Name))
                .Select(t => t.Name)
                .ToList();
            if (mine.Count == 0 && _kept.Cells.All(c => !c.IsAppCell))
            {
                return;
            }
            var asked = _shape;
            var arranged = await Workbench.ArrangeAsync(_kept.Cells.Select(c => c.ToSaved()).ToList(), mine, _kept.NextCell);
            if (asked != _shape)
            {
                // A cell was added, moved or deleted meanwhile: its number may be one the answer gave a table.
                await ArrangeTablesAsync();
                return;
            }
            Apply(arranged);
        }
        catch (ApiException)
        {
            // The server is away: the cells stay as they are.
        }
    }

    /// <summary>The server's order taken. Every cell already on screen is kept as it is (its editor, outputs and run
    /// number stay); an app cell takes the server's text; a cell the server adds is made.</summary>
    private void Apply(ArrangedNotebook arranged)
    {
        var byNumber = _kept.Cells.ToDictionary(c => c.Number);
        _kept.Cells = arranged.Cells
            .Select(a => byNumber.TryGetValue(a.Number, out var kept) ? Followed(kept, a) : Made(a))
            .ToList();
        _kept.NextCell = Math.Max(_kept.NextCell, arranged.NextCell);
    }

    private static CellModel Followed(CellModel kept, ArrangedCell arranged)
    {
        if (kept.IsAppCell || arranged.Role.Length > 0)
        {
            kept.Source = arranged.Source;
            kept.Role = arranged.Role;
            kept.Table = arranged.Table;
            kept.Grouped = arranged.Grouped;
        }
        return kept;
    }

    private static CellModel Made(ArrangedCell arranged) => new()
    {
        Kind = arranged.Kind,
        Source = arranged.Source,
        Number = arranged.Number,
        Role = arranged.Role,
        Table = arranged.Table,
        Grouped = arranged.Grouped,
    };

    /// <summary>A table open in Tables added to this document: its read-only cell (false: no such table is open).</summary>
    public async Task<bool> AddTableAsync(string table)
    {
        if ((await Workbench.TablesAsync()).Tables.All(t => t.Name != table))
        {
            return false;
        }
        _added.Add(table);
        await ArrangeTablesAsync();
        await OnChanged.InvokeAsync();
        StateHasChanged();
        return true;
    }

    /// <summary>Point the cells at another connection (unsaved until Save): a SQL or DAX cell's connection, and the
    /// name where code names it (sab.connection("..."), [Name].table).</summary>
    public async Task<int> RepointAsync(string from, string to)
    {
        var changed = 0;
        foreach (var cell in _kept.Cells.Where(c => !c.IsAppCell))
        {
            var before = (cell.Connection, cell.Source);
            if (cell.Connection == from)
            {
                cell.Connection = to;
            }
            cell.Source = cell.Source.Replace($"\"{from}\"", $"\"{to}\"", StringComparison.Ordinal).Replace($"[{from}]", $"[{to}]", StringComparison.Ordinal);
            changed += before != (cell.Connection, cell.Source) ? 1 : 0;
        }
        if (changed > 0)
        {
            await OnChanged.InvokeAsync();
            StateHasChanged();
        }
        return changed;
    }

    private void OnNotice(Notice notice)
    {
        if (notice.Type.StartsWith("dataset_", StringComparison.Ordinal) || notice.Type is "grid_updated" or "grid_closed")
        {
            _ = InvokeAsync(ArrangeSoonAsync);
        }
    }

    /// <summary>Notices come in bursts (a sample store sends one a table): the group is asked for once they settle.</summary>
    private async Task ArrangeSoonAsync()
    {
        var mine = ++_arrangeAsked;
        await Task.Delay(ArrangeSettlesMs);
        if (mine == _arrangeAsked)
        {
            await ArrangeTablesAsync();
            StateHasChanged();
        }
    }
}
