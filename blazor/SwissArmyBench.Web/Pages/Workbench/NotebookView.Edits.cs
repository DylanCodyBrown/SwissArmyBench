using Microsoft.AspNetCore.Components;
using Microsoft.AspNetCore.Components.Web;

using SwissArmyBench.Web.Components;
using SwissArmyBench.Web.State;

namespace SwissArmyBench.Web.Pages.Workbench;

// A notebook's cell commands (the classic workbenchNotebookCell.ts cell menu and workbenchNotebookEdits.ts): insert
// above or below, move, delete with Undo, duplicate, copy and paste, the kind, the name, clear and hide outputs, and
// the runs over part of the notebook (above, this and below, up to here). Each acts on the selected cell.
public partial class NotebookView
{
    // How many deletes and moves Undo goes back through.
    private const int UndoDepth = 20;

    private readonly Stack<List<CellModel>> _undo = new();
    private ShownMenu? _menu;
    private bool _snippet;

    /// <summary>Insert a snippet…: the snippets of the selected cell's language, then its form.</summary>
    public void PickSnippet() => _snippet = _selected is { IsAppCell: false };

    private string SnippetLanguage => _selected?.Kind switch
    {
        "dax" => "dax",
        "html" => "html",
        "markdown" => "markdown",
        "sql" => "sql",
        _ => "python",
    };

    private async Task SnippetInsertAsync(string text)
    {
        _snippet = false;
        if (_selected is { } cell && _views.TryGetValue(cell, out var view))
        {
            await view.InsertAsync(text);
        }
    }

    [Inject]
    private Notes Notes { get; set; } = default!;

    [Inject]
    private Dialogs Dialogs { get; set; } = default!;

    /// <summary>The cell copied for a paste into any notebook of the page (the classic cellClipboard.ts).</summary>
    private static CellModel? Copied { get; set; }

    /// <summary>The selected cell, or null.</summary>
    public CellModel? Selected => _selected;

    /// <summary>Whether a cell copied waits to be pasted.</summary>
    public static bool HasCopied => Copied is not null;

    private void KeepForUndo()
    {
        _undo.Push([.. _kept.Cells]);
        if (_undo.Count > UndoDepth)
        {
            var kept = _undo.Reverse().Skip(1).ToList();
            _undo.Clear();
            kept.ForEach(_undo.Push);
        }
    }

    /// <summary>Undo a cell's delete or move: the cells back as they were.</summary>
    public async Task UndoAsync()
    {
        if (_undo.TryPop(out var before))
        {
            _kept.Cells = before;
            _shape++;
            await OnChanged.InvokeAsync();
        }
    }

    public Task InsertAboveAsync() => AddCellAtAsync("code", _selected is null ? 0 : _kept.Cells.IndexOf(_selected));

    public Task InsertBelowAsync() => AddCellAsync("code");

    public Task MoveSelectedAsync(int by) => _selected is { IsAppCell: false } cell ? MoveAsync((cell, by)) : Task.CompletedTask;

    public async Task DeleteSelectedAsync()
    {
        if (_selected is { IsAppCell: false } cell)
        {
            await DeleteAsync(cell);
            await Notes.SayAsync("Cell deleted.");
        }
    }

    public async Task DuplicateAsync()
    {
        if (_selected is { IsAppCell: false } cell)
        {
            await PasteAsync(cell);
        }
    }

    /// <summary>The selected cell copied, for Paste below here or in another notebook of the page.</summary>
    public void CopySelected() => Copied = _selected is { IsAppCell: false } cell ? Clone(cell) : Copied;

    public Task PasteBelowAsync() => Copied is { } copied ? PasteAsync(copied) : Task.CompletedTask;

    private async Task PasteAsync(CellModel from)
    {
        var at = _selected is null ? _kept.Cells.Count : _kept.Cells.IndexOf(_selected) + 1;
        var made = Clone(from);
        made.Number = _kept.NextCell++;
        _kept.Cells.Insert(at, made);
        _shape++;
        _selected = made;
        await OnChanged.InvokeAsync();
    }

    private static CellModel Clone(CellModel cell) => new()
    {
        Kind = cell.Kind,
        Source = cell.Source,
        Connection = cell.Connection,
        Height = cell.Height,
        Number = cell.Number,
    };

    /// <summary>The selected cell made another kind (Python, SQL, Markdown, DAX, HTML).</summary>
    public async Task MakeKindAsync(string kind)
    {
        if (_selected is { IsAppCell: false } cell && cell.Kind != kind)
        {
            cell.Kind = kind;
            cell.Editing = kind is "markdown" or "html";
            await OnChanged.InvokeAsync();
        }
    }

    public async Task NameSelectedAsync()
    {
        if (_selected is not { IsAppCell: false } cell)
        {
            return;
        }
        if (await Dialogs.AskTextAsync("Name the cell", "A name for the cell (empty: no name).", "Cell name", cell.Name ?? string.Empty, "Name") is { } name)
        {
            cell.Name = name.Trim().Length == 0 ? null : name.Trim();
            await OnChanged.InvokeAsync();
        }
    }

    public void ClearAll() => _kept.Cells.ForEach(ClearOutput);

    public void ClearSelected()
    {
        if (_selected is { } cell)
        {
            ClearOutput(cell);
        }
    }

    private static void ClearOutput(CellModel cell)
    {
        cell.Outputs.Clear();
        cell.ErrorDetail = null;
        cell.ExecutionCount = null;
    }

    public void ToggleSelectedOutput()
    {
        if (_selected is { } cell)
        {
            cell.OutputHidden = !cell.OutputHidden;
        }
    }

    public Task RunSelectedAsync() => _selected is { } cell ? RunAsync(cell) : Task.CompletedTask;

    public Task RunAboveAsync() => RunRangeAsync(_kept.Cells.TakeWhile(c => c != _selected));

    public Task RunBelowAsync() => RunRangeAsync(_kept.Cells.SkipWhile(c => c != _selected));

    public Task RunUpToHereAsync() => RunRangeAsync(_kept.Cells.TakeWhile(c => c != _selected).Append(_selected!).Where(c => c is not null));

    private async Task RunRangeAsync(IEnumerable<CellModel> cells)
    {
        foreach (var cell in cells.Where(c => c.Kind != "markdown").ToList())
        {
            await RunAsync(cell);
            if (cell.Outputs.Any(o => OutputReader.Type(o) == "error"))
            {
                break;
            }
        }
    }

    private async Task DeleteCellAsync(CellModel cell)
    {
        await DeleteAsync(cell);
        await Notes.SayAsync("Cell deleted.");
    }

    private Task RunToAsync(CellModel cell)
    {
        _selected = cell;
        return RunUpToHereAsync();
    }

    /// <summary>Go to a cell by its number: selected and its editor focused.</summary>
    public async Task GoToCellAsync()
    {
        var typed = await Dialogs.AskTextAsync("Go to a cell", "The cell's number.", "Cell number", string.Empty, "Go");
        if (int.TryParse(typed, out var number) && _kept.Cells.FirstOrDefault(c => c.Number == number) is { } cell)
        {
            _selected = cell;
            _focusNext = cell;
        }
    }

    /// <summary>A cell's "More actions" menu (the classic cell menu).</summary>
    private void ShowCellMenu((CellModel Cell, MouseEventArgs At) asked)
    {
        _selected = asked.Cell;
        MenuEntry line(string label, string icon, Func<Task> run, string? disabled = null) => new(label, icon, run, disabled);
        Task now(Action act)
        {
            act();
            return Task.CompletedTask;
        }
        var user = !asked.Cell.IsAppCell;
        List<MenuEntry> entries =
        [
            line("Run the cells above", "play", RunAboveAsync),
            line("Run this cell and the ones below", "play", RunBelowAsync),
            MenuEntry.Separator,
            line("Insert a cell above", "plus", InsertAboveAsync),
            line("Insert a cell below", "plus", InsertBelowAsync),
            line("Name…", "edit", NameSelectedAsync, user ? null : "The app's cell keeps its own name"),
            line("Insert a snippet…", "plus", () => now(() => _snippet = true), user ? null : "The app's cell follows its table"),
            MenuEntry.Separator,
            line("Copy", "copy", () => now(CopySelected), user ? null : "The app's cell follows its table"),
            line("Paste below", "copy", PasteBelowAsync, HasCopied ? null : "Copy a cell first"),
            line("Duplicate", "copy", DuplicateAsync, user ? null : "The app's cell follows its table"),
            MenuEntry.Separator,
            line("Clear the output", "clean", () => now(ClearSelected)),
            line(asked.Cell.OutputHidden ? "Show the output" : "Hide the output", "eye", () => now(ToggleSelectedOutput)),
        ];
        _menu = new ShownMenu($"Cell {asked.Cell.Number}", entries, asked.At.ClientX, asked.At.ClientY + 4);
    }
}
