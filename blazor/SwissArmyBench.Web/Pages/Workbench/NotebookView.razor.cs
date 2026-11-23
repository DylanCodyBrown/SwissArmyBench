using Microsoft.AspNetCore.Components;

using SwissArmyBench.Web.Api;
using SwissArmyBench.Web.Api.Workbench;
using SwissArmyBench.Web.Components;
using SwissArmyBench.Web.State;

namespace SwissArmyBench.Web.Pages.Workbench;

public partial class NotebookView
{
    private readonly Dictionary<CellModel, NotebookCellView> _views = [];
    private List<CellModel> _cells = [];
    private CellModel? _selected;
    private int _nextCell = 1;
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

    [Parameter]
    public IReadOnlyList<string> Connections { get; set; } = [];

    /// <summary>The notebook changed since it was opened or saved.</summary>
    [Parameter]
    public EventCallback OnChanged { get; set; }

    /// <summary>A key the page acts on (save, saveAs).</summary>
    [Parameter]
    public EventCallback<string> OnPageKey { get; set; }

    /// <summary>The cells as the file keeps them, and the number the next new cell gets.</summary>
    public (IReadOnlyList<NotebookCell> Cells, int NextCell) ToSave() => (_cells.Select(c => c.ToSaved()).ToList(), _nextCell);

    protected override async Task OnInitializedAsync()
    {
        _runner = new CellRunner(Workbench, Session);
        _cells = (Opened?.Cells ?? []).Select(CellModel.From).ToList();
        _nextCell = Math.Max(Opened?.NextCell ?? 1, _cells.Select(c => c.Number + 1).DefaultIfEmpty(1).Max());
        Live.NoticeArrived += OnNotice;
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
        var at = _cells.IndexOf(cell);
        var code = _cells.Select(c => c.Kind == "code" ? c.Source : string.Empty).ToList();
        return new IntelContext(Session.Kernel, Path, Session.Python, true, code.Take(at).ToList(), code.Skip(at + 1).ToList(), Path ?? "untitled.ipynb", cell.Connection);
    }

    private async Task AddCellAsync(string kind)
    {
        var at = _selected is null ? _cells.Count : _cells.IndexOf(_selected) + 1;
        var cell = new CellModel { Kind = kind, Number = _nextCell++, Editing = kind == "markdown" };
        _cells.Insert(at, cell);
        _shape++;
        _selected = cell;
        _focusNext = cell;
        await OnChanged.InvokeAsync();
    }

    private Task ChangedAsync(CellModel cell) => OnChanged.InvokeAsync();

    private async Task MoveAsync((CellModel Cell, int By) move)
    {
        var at = _cells.IndexOf(move.Cell);
        var to = at + move.By;
        if (to < 0 || to >= _cells.Count)
        {
            return;
        }
        (_cells[at], _cells[to]) = (_cells[to], _cells[at]);
        _shape++;
        await OnChanged.InvokeAsync();
    }

    private async Task DeleteAsync(CellModel cell)
    {
        _cells.Remove(cell);
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
        var at = _cells.IndexOf(cell);
        if (key == "runInsert" || (key == "run" && at == _cells.Count - 1))
        {
            await AddCellAsync("code");
        }
        else if (key == "run" && at >= 0)
        {
            _selected = _cells[at + 1];
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
            _error = null;
        }
        catch (ApiException error)
        {
            _error = error;
        }
        await OnChanged.InvokeAsync();
    }

    private async Task RunAllAsync()
    {
        _runningAll = true;
        foreach (var cell in _cells.Where(c => c.Kind != "markdown").ToList())
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
