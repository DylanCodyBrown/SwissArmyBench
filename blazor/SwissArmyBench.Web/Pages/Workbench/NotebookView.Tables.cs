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

    // Counts the changes to the cells' list (added, moved, deleted): an arrange asked before one is asked again.
    private int _shape;

    private bool IsData => Path is { } path && path.Replace('\\', '/').EndsWith("/data.ipynb", StringComparison.OrdinalIgnoreCase);

    private async Task ArrangeTablesAsync()
    {
        try
        {
            var open = (await Workbench.TablesAsync()).Tables;
            var mine = open
                .Where(t => t.Document == Path || (IsData && t.Document is null) || _cells.Any(c => c.IsAppCell && c.Table == t.Name))
                .Select(t => t.Name)
                .ToList();
            if (mine.Count == 0 && _cells.All(c => !c.IsAppCell))
            {
                return;
            }
            var asked = _shape;
            var arranged = await Workbench.ArrangeAsync(_cells.Select(c => c.ToSaved()).ToList(), mine, _nextCell);
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
        var byNumber = _cells.ToDictionary(c => c.Number);
        _cells = arranged.Cells
            .Select(a => byNumber.TryGetValue(a.Number, out var kept) ? Followed(kept, a) : Made(a))
            .ToList();
        _nextCell = Math.Max(_nextCell, arranged.NextCell);
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
