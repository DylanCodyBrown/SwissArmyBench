using Microsoft.AspNetCore.Components;

using SwissArmyBench.Web.Api;
using SwissArmyBench.Web.Api.Workbench;
using SwissArmyBench.Web.Components;
using SwissArmyBench.Web.State;

namespace SwissArmyBench.Web.Pages.Workbench;

public partial class NotebookView
{
    private readonly Dictionary<CellModel, NotebookCellView> _views = [];
    private NotebookKept _kept = new();
    private CellModel? _selected;
    private bool _runningAll;
    private Exception? _error;
    private CellRunner? _runner;

    // The cell whose editor takes the focus once it is drawn (a new cell, or the next after Shift+Enter).
    private CellModel? _focusNext;

    [Inject]
    private WorkbenchClient Workbench { get; set; } = default!;

    [Inject]
    private PythonSession Session { get; set; } = default!;

    [Inject]
    private LiveUpdates Live { get; set; } = default!;

    /// <summary>The notebook as opened (null: a new one, not saved yet).</summary>
    [Parameter]
    public OpenedNotebook? Opened { get; set; }

    /// <summary>Where it is saved (null until Save as).</summary>
    [Parameter]
    public string? Path { get; set; }

    /// <summary>Its cells kept with its document (a tab moved keeps them).</summary>
    [Parameter]
    public NotebookKept? Kept { get; set; }

    [Parameter]
    public IReadOnlyList<string> Connections { get; set; } = [];

    /// <summary>The notebook changed since it was opened or saved.</summary>
    [Parameter]
    public EventCallback OnChanged { get; set; }

    /// <summary>A key the page acts on (save, saveAs).</summary>
    [Parameter]
    public EventCallback<string> OnPageKey { get; set; }

    /// <summary>Run all is going (its button greyed out meanwhile).</summary>
    public bool RunningAll => _runningAll;

    /// <summary>The cells as the file keeps them, and the number the next new cell gets.</summary>
    public (IReadOnlyList<NotebookCell> Cells, int NextCell) ToSave() => (_kept.Cells.Select(c => c.ToSaved()).ToList(), _kept.NextCell);

    protected override async Task OnInitializedAsync()
    {
        _runner = new CellRunner(Workbench, Session);
        Live.NoticeArrived += OnNotice;
        _kept = Kept ?? new NotebookKept();
        if (_kept.Started)
        {
            return; // drawn again (its tab moved): its cells as they were
        }
        _kept.Started = true;
        _kept.Cells = (Opened?.Cells ?? []).Select(CellModel.From).ToList();
        _kept.NextCell = Math.Max(Opened?.NextCell ?? 1, _kept.Cells.Select(c => c.Number + 1).DefaultIfEmpty(1).Max());
        await ArrangeTablesAsync();
    }

    /// <summary>A blade's line put into the selected cell (a new Python cell when none is).</summary>
    public async Task InsertAsync(string text)
    {
        if (_selected is null || _selected.IsAppCell)
        {
            await AddCellAsync("code");
        }
        if (_selected is not null && _views.TryGetValue(_selected, out var view))
        {
            await view.InsertAsync(text);
        }
    }

    private void Select(CellModel cell) => _selected = cell;

    /// <summary>What the editor's intelligence knows of the notebook: the code of the cells above and below.</summary>
    private IntelContext IntelFor(CellModel cell)
    {
        var at = _kept.Cells.IndexOf(cell);
        var code = _kept.Cells.Select(c => c.Kind == "code" ? c.Source : string.Empty).ToList();
        return new IntelContext(Session.Kernel, Path, Session.Python, true, code.Take(at).ToList(), code.Skip(at + 1).ToList(), Path ?? "untitled.ipynb", cell.Connection);
    }

    /// <summary>A new cell of a kind under the selected one (at the end when none is).</summary>
    public Task AddCellAsync(string kind) => AddCellAtAsync(kind, _selected is null ? _kept.Cells.Count : _kept.Cells.IndexOf(_selected) + 1);

    private async Task AddCellAtAsync(string kind, int at)
    {
        var cell = new CellModel { Kind = kind, Number = _kept.NextCell++, Editing = kind is "markdown" or "html" };
        _kept.Cells.Insert(at, cell);
        _shape++;
        _selected = cell;
        _focusNext = cell;
        await OnChanged.InvokeAsync();
    }

    private Task ChangedAsync(CellModel cell) => OnChanged.InvokeAsync();

    private async Task MoveAsync((CellModel Cell, int By) move)
    {
        KeepForUndo();
        var at = _kept.Cells.IndexOf(move.Cell);
        var to = at + move.By;
        if (to < 0 || to >= _kept.Cells.Count)
        {
            return;
        }
        (_kept.Cells[at], _kept.Cells[to]) = (_kept.Cells[to], _kept.Cells[at]);
        _shape++;
        await OnChanged.InvokeAsync();
    }

    private async Task DeleteAsync(CellModel cell)
    {
        KeepForUndo();
        _kept.Cells.Remove(cell);
        _shape++;
        _views.Remove(cell);
        _selected = null;
        await OnChanged.InvokeAsync();
    }

    /// <summary>Shift+Enter runs and goes to the next cell (a new one at the end); Ctrl+Enter runs and stays; Alt+Enter
    /// runs and puts a new cell under it. Save keys go to the page.</summary>
    private async Task KeyAsync((CellModel Cell, EditorKey Key) pressed)
    {
        var (cell, key) = pressed;
        switch (key.Name)
        {
            case "save" or "saveAs":
                await OnPageKey.InvokeAsync(key.Name);
                return;
            case "run" or "runHere" or "runInsert":
                _selected = cell;
                await OnChanged.InvokeAsync();
                await RunAsync(cell);
                await AfterRunAsync(cell, key.Name);
                return;
            default:
                return;
        }
    }

    private async Task AfterRunAsync(CellModel cell, string key)
    {
        var at = _kept.Cells.IndexOf(cell);
        if (key == "runInsert" || (key == "run" && at == _kept.Cells.Count - 1))
        {
            await AddCellAsync("code");
        }
        else if (key == "run" && at >= 0)
        {
            _selected = _kept.Cells[at + 1];
        }
        _focusNext = _selected;
    }

    protected override async Task OnAfterRenderAsync(bool firstRender)
    {
        if (_focusNext is { } cell && _views.TryGetValue(cell, out var view))
        {
            _focusNext = null;
            await view.FocusAsync();
        }
    }

    private async Task RunAsync(CellModel cell)
    {
        if (cell.Kind == "markdown" || _runner is null)
        {
            cell.Editing = false;
            return;
        }
        var request = cell.Role == "transformations" && cell.Table is { } table
            ? new RunRequest(cell.Source, "table", Table: table, Document: Path)
            : new RunRequest(cell.Source, cell.Kind, cell.Kind is "sql" or "dax" ? cell.Connection : null, Document: Path);
        try
        {
            await _runner.RunAsync(cell, request, Path, () => InvokeAsync(StateHasChanged));
            cell.Editing = cell.Kind != "html" && cell.Editing; // an HTML cell shows its design once run
            _error = null;
        }
        catch (ApiException error)
        {
            _error = error;
        }
        await OnChanged.InvokeAsync();
    }

    /// <summary>Every cell from the top, stopping at an error (the cells after it would read what it did not make).</summary>
    public async Task RunAllAsync()
    {
        _runningAll = true;
        foreach (var cell in _kept.Cells.Where(c => c.Kind != "markdown").ToList())
        {
            await RunAsync(cell);
            if (cell.Outputs.Any(o => OutputReader.Type(o) == "error"))
            {
                break; // the cells after it would read what it did not make
            }
        }
        _runningAll = false;
    }

    private Task AnswerAsync((CellModel Cell, string Line) answer) => _runner?.AnswerAsync(answer.Cell, answer.Line) ?? Task.CompletedTask;

    public void Dispose() => Live.NoticeArrived -= OnNotice;
}
