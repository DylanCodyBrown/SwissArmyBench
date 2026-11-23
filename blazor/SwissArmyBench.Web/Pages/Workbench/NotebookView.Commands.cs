namespace SwissArmyBench.Web.Pages.Workbench;

// What the palette asks of a notebook (the classic workbenchCommandList.ts's cell, tables and html commands): edit
// the selected cell, the run order in words, a table's cell run or gone to, the HTML cells run, an HTML pane sized.
public partial class NotebookView
{
    /// <summary>Edit the selected cell (an HTML or Markdown cell that shows as drawn): its editor in place.</summary>
    public Task EditSelectedAsync()
    {
        if (_selected is { IsAppCell: false } cell)
        {
            cell.Editing = true;
            _focusNext = cell;
            StateHasChanged();
        }
        return Task.CompletedTask;
    }

    /// <summary>A first cell with this text (New environment's imports): at the top, selected.</summary>
    public async Task AddFirstCellAsync(string kind, string source)
    {
        var cell = new CellModel { Kind = kind, Source = source, Number = _kept.NextCell++ };
        _kept.Cells.Insert(0, cell);
        (_shape, _selected) = (_shape + 1, cell);
        await OnChanged.InvokeAsync();
        StateHasChanged();
    }

    /// <summary>The run order: each cell's state (notRun, edited, outOfDate), a line each.</summary>
    public string RunOrderText() => string.Join('\n', (_flow?.Cells ?? []).Select(c => $"[{c.Number}] {c.State}"));

    public Task RunTableNamedAsync(string table) => RunTableAsync(table);

    /// <summary>A table's cell selected (false: this document holds none for it).</summary>
    public async Task<bool> GoToTableAsync(string table) =>
        TableCell(table) is { } cell && await GoToCellNumberAsync(cell.Number);

    /// <summary>Every HTML cell run (its names filled from the kernel).</summary>
    public async Task RunHtmlCellsAsync()
    {
        foreach (var cell in HtmlCells().ToList())
        {
            await RunAsync(cell);
        }
    }

    /// <summary>The selected HTML cell's pane sized (null: the design's own height).</summary>
    public void ResizeSelectedHtml(int? height)
    {
        if (_selected is { Kind: "html" } cell)
        {
            cell.Height = height;
            StateHasChanged();
            _ = OnChanged.InvokeAsync();
        }
    }

    /// <summary>Each user cell's editor with its place ("cell 3"), for the status bar's Problems list.</summary>
    public IReadOnlyList<(string Place, SwissArmyBench.Web.Components.CodeEditor Editor, CellModel Cell)> Editors() =>
        _kept.Cells
            .Where(c => !c.IsAppCell && _views.ContainsKey(c) && _views[c].Editor is not null)
            .Select(c => ($"cell {c.Number}", _views[c].Editor!, c))
            .ToList();

    /// <summary>A problem's place shown: its cell selected, then its line.</summary>
    public async Task RevealAsync(CellModel cell, int line, int col)
    {
        _selected = cell;
        StateHasChanged();
        if (_views.TryGetValue(cell, out var view) && view.Editor is { } editor)
        {
            await editor.RevealAsync(line, col);
        }
    }
}
