namespace SwissArmyBench.Web.Pages.Workbench;

// The Tables group's folds (the classic workbenchNotebookTables.ts): the group's heading folds every cell of the
// group, a table's heading folds its maker and its read-only cell; each opens unfolded, the user's fold then stays.
public partial class NotebookView
{
    private readonly HashSet<string> _foldedTables = [];
    private bool _groupFolded;

    /// <summary>Lineage: a cell (its number) back to the data, with its values.</summary>
    [Microsoft.AspNetCore.Components.Parameter]
    public Microsoft.AspNetCore.Components.EventCallback<int> OnLineage { get; set; }

    /// <summary>A cell by its number selected and its editor focused (a lineage's node, an @cell link).</summary>
    public async Task<bool> GoToCellNumberAsync(int number)
    {
        if (_kept.Cells.All(c => c.Number != number))
        {
            return false;
        }
        await GoToNumberAsync(number);
        StateHasChanged();
        return true;
    }

    /// <summary>F1: help on the name at the cursor of the selected cell.</summary>
    public Task<string?> HelpAsync() => _selected is not null && _views.TryGetValue(_selected, out var view) ? view.HelpAsync() : Task.FromResult<string?>(null);

    private int TableCount => _kept.Cells.Count(c => c.Role == "table");

    private bool IsFolded(CellModel cell) => cell.Role == "tables" ? _groupFolded : _foldedTables.Contains(cell.Table ?? string.Empty);

    /// <summary>A cell the group's or its table's fold puts away.</summary>
    private bool FoldedAway(CellModel cell) =>
        (cell.Grouped && cell.Role != "tables" && _groupFolded)
        || (cell.Grouped && cell.Table is { } table && cell.Role is "maker" or "transformations" && _foldedTables.Contains(table));

    private void ToggleFold(CellModel cell)
    {
        if (cell.Role == "tables")
        {
            _groupFolded = !_groupFolded;
        }
        else if (cell.Table is { } table && !_foldedTables.Remove(table))
        {
            _foldedTables.Add(table);
        }
    }

    private CellModel? TableCell(string? table) =>
        _kept.Cells.FirstOrDefault(c => c.Role == "transformations" && c.Table == table);

    /// <summary>A table's Run: its read-only cell run again.</summary>
    private Task RunTableAsync(string table) => TableCell(table) is { } cell ? RunAsync(cell) : Task.CompletedTask;

    /// <summary>Fold or open the Tables group, or one table (the palette's tables.fold and tables.unfold).</summary>
    public void FoldTables(bool fold, string? table = null)
    {
        if (table is null)
        {
            _groupFolded = fold;
        }
        else if (fold)
        {
            _foldedTables.Add(table);
        }
        else
        {
            _foldedTables.Remove(table);
        }
        StateHasChanged();
    }

    /// <summary>Every table's read-only cell run again (the Tables tool's Run tables).</summary>
    public async Task RunTablesAsync()
    {
        foreach (var cell in _kept.Cells.Where(c => c.Role == "transformations").ToList())
        {
            await RunAsync(cell);
        }
    }

    /// <summary>The document's tables and each one's cell (the palette's tables.list).</summary>
    public IReadOnlyList<(string Table, int Cell)> TablesShown() =>
        _kept.Cells.Where(c => c.Role == "transformations" && c.Table is not null).Select(c => (c.Table!, c.Number)).ToList();

    /// <summary>The HTML cells (the palette's html.list and html.run).</summary>
    public IReadOnlyList<CellModel> HtmlCells() => _kept.Cells.Where(c => c.Kind == "html").ToList();
}
