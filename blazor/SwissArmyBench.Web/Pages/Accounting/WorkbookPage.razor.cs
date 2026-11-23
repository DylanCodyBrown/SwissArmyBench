using Microsoft.AspNetCore.Components;
using Microsoft.JSInterop;

using SwissArmyBench.Web.Api;
using SwissArmyBench.Web.Api.Accounting;
using SwissArmyBench.Web.State;

namespace SwissArmyBench.Web.Pages.Accounting;

/// <summary>The Excel canvas (the classic excelCanvas.ts, the Accounting extension's plug-in): the design is the
/// server's, every change a route, and what comes back is drawn. Undo and Redo keep the designs before each change
/// (the classic canvasKit.ts history) and send one back whole.</summary>
public partial class WorkbookPage : IAsyncDisposable
{
    // Undo keeps this many designs.
    private const int HistoryDepth = 100;

    // The server forgot the design (it restarted): 404 with "not open".
    private const int NotFound = 404;

    private readonly Stack<WorkbookDesign> _undo = new();
    private readonly Stack<WorkbookDesign> _redo = new();
    private WorkbookState? _state;
    private string? _sheetId;
    private string? _selected;
    private bool _playing;
    private bool _building;
    private bool _landing;
    private string? _opened;
    private IReadOnlyList<string> _openTables = [];
    private Exception? _error;
    private WorkbookMenu? _menu;
    private bool _templatesOpen;
    private string? _statementsFor;
    private bool _statementsOpen;
    private ElementReference _blocksButton;
    private ElementReference _templatesButton;
    private IJSObjectReference? _module;

    [Inject]
    private AccountingClient Accounting { get; set; } = default!;

    [Inject]
    private LiveUpdates Live { get; set; } = default!;

    [Inject]
    private Notes Notes { get; set; } = default!;

    [Inject]
    private IJSRuntime Js { get; set; } = default!;

    [Inject]
    private SwissArmyBench.Web.Api.Files.FileChooser Files { get; set; } = default!;

    /// <summary>The design's file (a workbook.design.json); null with NewTitle: a new design.</summary>
    [Parameter]
    public string? Path { get; set; }

    /// <summary>A new design's title (the first sheet's heading): the project's name, else the tab's.</summary>
    [Parameter]
    public string? NewTitle { get; set; }

    /// <summary>The design saved: its file (the tab takes its name).</summary>
    [Parameter]
    public EventCallback<string> OnSaved { get; set; }

    /// <summary>Unsaved changes or none (the tab's dot).</summary>
    [Parameter]
    public EventCallback<bool> OnDirty { get; set; }

    private WorkbookSheet? Sheet => _state?.Design.Sheets.FirstOrDefault(s => s.Id == _sheetId) ?? _state?.Design.Sheets.FirstOrDefault();

    private WorkbookBlock? Selected => Sheet?.Blocks.FirstOrDefault(b => b.Id == _selected);

    protected override void OnInitialized() => Live.NoticeArrived += OnNotice;

    /// <summary>A design named in the address (a file, or a new one by its title); none: the landing.</summary>
    protected override async Task OnParametersSetAsync()
    {
        var wanted = Path ?? (NewTitle is null ? null : "new:" + NewTitle);
        _landing = wanted is null;
        if (wanted is null || wanted == _opened)
        {
            return;
        }
        _opened = wanted;
        await CloseOpenAsync();
        _undo.Clear();
        _redo.Clear();
        _playing = false;
        _selected = null;
        try
        {
            var body = Path is null ? new Dictionary<string, object?> { ["title"] = NewTitle } : new Dictionary<string, object?> { ["path"] = Path };
            Take(await Accounting.OpenAsync(body));
            _openTables = await Accounting.OpenTablesAsync();
        }
        catch (ApiException error)
        {
            _error = error;
        }
    }

    private void Take(WorkbookState next)
    {
        if (next.Unsaved != (_state?.Unsaved ?? false))
        {
            _ = OnDirty.InvokeAsync(next.Unsaved);
        }
        _state = next;
        if (!next.Design.Sheets.Any(s => s.Id == _sheetId))
        {
            _sheetId = next.Design.Sheets.FirstOrDefault()?.Id;
        }
        if (_selected is not null && !next.Design.Sheets.Any(s => s.Blocks.Any(b => b.Id == _selected)))
        {
            _selected = null;
        }
    }

    /// <summary>A route under the design; a design the server forgot is opened again as it is here first.</summary>
    private async Task<WorkbookState> CallAsync(HttpMethod method, string route, object? body = null)
    {
        var state = _state ?? throw new InvalidOperationException("No design is open.");
        try
        {
            var done = await Accounting.SendAsync(state.Id, method, route, body);
            Take(done);
            return done;
        }
        catch (ApiException error) when (error.Status == NotFound && error.Message.Contains("not open", StringComparison.Ordinal))
        {
            Take(await Accounting.OpenAsync(new Dictionary<string, object?> { ["design"] = state.Design, ["title"] = state.Title }));
            var done = await Accounting.SendAsync(_state!.Id, method, route, body);
            Take(done);
            return done;
        }
    }

    /// <summary>A change of the design: sent, drawn; Undo can take it back. A refusal shows where it happened.</summary>
    private async Task<WorkbookState?> ChangeAsync(HttpMethod method, string route, object? body = null)
    {
        var before = _state?.Design;
        try
        {
            _error = null;
            var done = await CallAsync(method, route, body);
            if (before is not null)
            {
                Remember(_undo, before);
                _redo.Clear();
            }
            return done;
        }
        catch (ApiException error)
        {
            _error = error;
            return null;
        }
        finally
        {
            StateHasChanged();
        }
    }

    private static void Remember(Stack<WorkbookDesign> stack, WorkbookDesign design)
    {
        stack.Push(design);
        if (stack.Count > HistoryDepth)
        {
            var kept = stack.Take(HistoryDepth).Reverse().ToList();
            stack.Clear();
            kept.ForEach(stack.Push);
        }
    }

    private Task UndoAsync() => StepAsync(_undo, _redo);

    private Task RedoAsync() => StepAsync(_redo, _undo);

    private async Task StepAsync(Stack<WorkbookDesign> from, Stack<WorkbookDesign> to)
    {
        if (_state is null || !from.TryPop(out var design))
        {
            return;
        }
        var now = _state.Design;
        try
        {
            await CallAsync(HttpMethod.Put, string.Empty, new { design });
            Remember(to, now);
        }
        catch (ApiException error)
        {
            from.Push(design);
            _error = error;
        }
        StateHasChanged();
    }

    private Task<WorkbookState?> PatchAsync(string block, IReadOnlyDictionary<string, object?> body) =>
        ChangeAsync(HttpMethod.Patch, $"/blocks/{Uri.EscapeDataString(block)}", body);

    private Task<WorkbookState?> SheetAsync(string sheet, IReadOnlyDictionary<string, object?> body) =>
        ChangeAsync(HttpMethod.Patch, $"/sheets/{Uri.EscapeDataString(sheet)}", body);

    private Task RemoveBlockAsync(string block) => ChangeAsync(HttpMethod.Delete, $"/blocks/{Uri.EscapeDataString(block)}");

    private async Task SelectAsync(string? block)
    {
        if (block is not null && block != _selected)
        {
            _openTables = await Accounting.OpenTablesAsync();
        }
        _selected = block;
    }

    // Another window's or the agent's change: drawn again only when the design is not the one shown.
    private void OnNotice(Notice notice)
    {
        if (notice.Type == "workbook_changed" && _state is { } state && notice.Text("id") == state.Id)
        {
            _ = InvokeAsync(() => HeardAsync(state));
        }
    }

    private async Task HeardAsync(WorkbookState shown)
    {
        try
        {
            var next = await Accounting.GetAsync(shown.Id);
            if (!ReferenceEquals(_state, shown))
            {
                return;
            }
            var same = System.Text.Json.JsonSerializer.Serialize(next.Design, ApiClient.Json) == System.Text.Json.JsonSerializer.Serialize(shown.Design, ApiClient.Json);
            if (!same || next.Played != shown.Played)
            {
                Take(next);
                StateHasChanged();
            }
        }
        catch (ApiException)
        {
            // Closed meanwhile: nothing to follow.
        }
    }

    private async Task CloseOpenAsync()
    {
        if (_state is { } state)
        {
            _state = null;
            try
            {
                await Accounting.CloseAsync(state.Id);
            }
            catch (ApiException)
            {
                // Gone already.
            }
        }
    }

    public async ValueTask DisposeAsync()
    {
        Live.NoticeArrived -= OnNotice;
        await CloseOpenAsync();
        if (_module is not null)
        {
            try
            {
                await _module.DisposeAsync();
            }
            catch (JSDisconnectedException)
            {
                // The page is going.
            }
        }
    }
}
