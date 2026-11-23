using System.Text.Json;

using Microsoft.AspNetCore.Components;
using Microsoft.JSInterop;

using SwissArmyBench.Web.Api;
using SwissArmyBench.Web.Api.Grids;

namespace SwissArmyBench.Web.Components;

public partial class AgGrid
{
    private ElementReference _host;
    private IJSObjectReference? _module;
    private IJSObjectReference? _grid;
    private DotNetObjectReference<AgGrid>? _self;
    private string? _mounted;
    private string _sentCompare = "null";
    private string _sentOnly = "null";
    private string _sentKeys = "null";
    private int? _sentUpto;

    [Inject]
    private IJSRuntime Js { get; set; } = default!;

    /// <summary>The server's grid id.</summary>
    [Parameter, EditorRequired]
    public string GridId { get; set; } = string.Empty;

    [Parameter, EditorRequired]
    public IReadOnlyList<GridColumn> Columns { get; set; } = [];

    /// <summary>Compare mode: this side's rows from a compare (null: the grid's own rows).</summary>
    [Parameter]
    public CompareView? Compare { get; set; }

    /// <summary>Only these columns shown (null: every one): diff mode's keys and the columns that differ.</summary>
    [Parameter]
    public IReadOnlyList<string>? OnlyColumns { get; set; }

    /// <summary>A step's preview: the rows after the first Upto steps (null: the whole view).</summary>
    [Parameter]
    public int? Upto { get; set; }

    /// <summary>The compare rows sharing a picked row's key, lit up (null: none).</summary>
    [Parameter]
    public KeyGroup? KeyRows { get; set; }

    /// <summary>A header's name was clicked (its column is selected too).</summary>
    [Parameter]
    public EventCallback<string> OnHeaderClicked { get; set; }

    /// <summary>The rows in the view, as the server counted them.</summary>
    [Parameter]
    public EventCallback<long> OnCounted { get; set; }

    /// <summary>The view changed from the grid itself (a header's sort).</summary>
    [Parameter]
    public EventCallback OnChanged { get; set; }

    [Parameter]
    public EventCallback<string> OnFailed { get; set; }

    [Parameter]
    public EventCallback<GridSelection> OnSelectionChanged { get; set; }

    [Parameter]
    public EventCallback<GridPoint> OnCellMenu { get; set; }

    [Parameter]
    public EventCallback<GridPoint> OnHeaderMenu { get; set; }

    /// <summary>A compared grid's row was clicked (its position in the compare): its key's rows light up, or (cross
    /// compare) the other side is filtered to its key.</summary>
    [Parameter]
    public EventCallback<long> OnRowPicked { get; set; }

    /// <summary>The rows on screen changed (the first and the last, view positions).</summary>
    [Parameter]
    public EventCallback<(long First, long Last)> OnShown { get; set; }

    /// <summary>A cell opened (a double-click, Enter or F2 on it): the value viewer shows its value.</summary>
    [Parameter]
    public EventCallback<GridPoint> OnCellOpened { get; set; }

    /// <summary>Words the grid has for the user (Ctrl+C's "Copied 4 rows × 2 columns.").</summary>
    [Parameter]
    public EventCallback<string> OnSaid { get; set; }

    protected override async Task OnAfterRenderAsync(bool firstRender)
    {
        if (_mounted == GridId)
        {
            await SyncAsync();
            return;
        }
        _mounted = GridId; // before the awaits: a render meanwhile must not mount a second grid
        _module ??= await Js.InvokeAsync<IJSObjectReference>("import", "./js/agGrid.js");
        if (_grid is not null)
        {
            await _grid.InvokeVoidAsync("destroy");
            await _grid.DisposeAsync();
        }
        _self ??= DotNetObjectReference.Create(this);
        _grid = await _module.InvokeAsync<IJSObjectReference>("mount", _host, _self, GridId, Columns, ApiClient.ClientId);
        _sentCompare = _sentOnly = _sentKeys = "null";
        _sentUpto = null;
        await SyncAsync();
    }

    /// <summary>The compare, the columns shown and the lit key rows sent to the grid when they changed.</summary>
    private async Task SyncAsync()
    {
        if (_grid is null)
        {
            return;
        }
        var compare = JsonSerializer.Serialize(Compare is null ? null : new { id = Compare.Id, side = Compare.Side });
        if (compare != _sentCompare)
        {
            _sentCompare = compare;
            _sentKeys = "null";
            await _grid.InvokeVoidAsync("setCompare", Compare is null ? null : new { id = Compare.Id, side = Compare.Side });
        }
        if (Upto != _sentUpto)
        {
            _sentUpto = Upto;
            await _grid.InvokeVoidAsync("setUpto", Upto);
        }
        var only = JsonSerializer.Serialize(OnlyColumns);
        if (only != _sentOnly)
        {
            _sentOnly = only;
            await _grid.InvokeVoidAsync("showOnly", OnlyColumns);
        }
        var keys = JsonSerializer.Serialize(KeyRows is null ? null : new { first = KeyRows.First, last = KeyRows.Last });
        if (keys != _sentKeys)
        {
            _sentKeys = keys;
            await _grid.InvokeVoidAsync("setKeyRows", KeyRows is null ? null : new { first = KeyRows.First, last = KeyRows.Last });
        }
    }

    /// <summary>The grid's steps changed: its columns again, every row asked for anew, the selection cleared.</summary>
    public async Task RefreshAsync(IReadOnlyList<GridColumn> columns)
    {
        if (_grid is not null)
        {
            await _grid.InvokeVoidAsync("refresh", columns);
            _sentOnly = "null"; // a new view shows every column until the next sync hides them again
        }
    }

    /// <summary>Each column named (none: every column) as wide as its values.</summary>
    public async Task AutoSizeAsync(IReadOnlyList<string> columns)
    {
        if (_grid is not null)
        {
            await _grid.InvokeVoidAsync("autoSize", columns);
        }
    }

    /// <summary>The selection's values in one column (the clicked cell's when one is), for Keep these.</summary>
    public async Task<IReadOnlyList<JsonElement>> ValuesAsync(string column) =>
        _grid is null ? [] : await _grid.InvokeAsync<List<JsonElement>>("values", column);

    /// <summary>One cell's value (from the rows loaded, else asked of the server).</summary>
    public async Task<JsonElement> CellAsync(long row, string column) =>
        _grid is null ? default : await _grid.InvokeAsync<JsonElement>("cell", row, column);

    /// <summary>A loaded row's values, column by column in the view's order.</summary>
    public async Task<IReadOnlyList<(string Column, JsonElement Value)>> RowValuesAsync(long row)
    {
        if (_grid is null)
        {
            return [];
        }
        var pairs = await _grid.InvokeAsync<List<List<JsonElement>>>("rowValues", row);
        return pairs.Select(p => (p[0].GetString() ?? string.Empty, p[1])).ToList();
    }

    /// <summary>The selected rows' positions (rows or cells selected), up to `most`.</summary>
    public async Task<IReadOnlyList<long>> SelectedRowsAsync(int most) =>
        _grid is null ? [] : await _grid.InvokeAsync<List<long>>("selectedRows", most);

    /// <summary>The selection on the clipboard (plain, headers or markdown); the words to say, or null.</summary>
    public async Task<string?> CopyAsync(string style) => _grid is null ? null : await _grid.InvokeAsync<string?>("copy", style);

    public async Task RevealColumnAsync(string column)
    {
        if (_grid is not null)
        {
            await _grid.InvokeVoidAsync("revealColumn", column);
        }
    }

    /// <summary>This grid and `other` keep one vertical position (two aligned grids); what lets go of them, or null
    /// when either is not drawn yet.</summary>
    public async Task<IJSObjectReference?> LockScrollAsync(AgGrid other)
    {
        if (_module is null || _grid is null || other._grid is null)
        {
            return null;
        }
        return await _module.InvokeAsync<IJSObjectReference>("lockScroll", _grid, other._grid);
    }

    [JSInvokable]
    public Task CellOpened(long row, string column, double x, double y) => OnCellOpened.InvokeAsync(new GridPoint(row, column, x, y));

    [JSInvokable]
    public Task Shown(long first, long last) => OnShown.InvokeAsync((first, last));

    [JSInvokable]
    public Task RowPicked(long row) => OnRowPicked.InvokeAsync(row);

    [JSInvokable]
    public Task HeaderClicked(string column) => OnHeaderClicked.InvokeAsync(column);

    [JSInvokable]
    public Task Counted(long rows) => OnCounted.InvokeAsync(rows);

    [JSInvokable]
    public Task Changed() => OnChanged.InvokeAsync();

    [JSInvokable]
    public Task Failed(string words) => OnFailed.InvokeAsync(words);

    [JSInvokable]
    public Task SelectionChanged(GridSelection selection) => OnSelectionChanged.InvokeAsync(selection);

    [JSInvokable]
    public Task CellMenu(long row, string column, double x, double y) => OnCellMenu.InvokeAsync(new GridPoint(row, column, x, y));

    [JSInvokable]
    public Task HeaderMenu(string column, double x, double y) => OnHeaderMenu.InvokeAsync(new GridPoint(-1, column, x, y));

    [JSInvokable]
    public Task Said(string words) => OnSaid.InvokeAsync(words);

    public async ValueTask DisposeAsync()
    {
        if (_grid is not null)
        {
            await _grid.InvokeVoidAsync("destroy");
            await _grid.DisposeAsync();
        }
        if (_module is not null)
        {
            await _module.DisposeAsync();
        }
        _self?.Dispose();
        GC.SuppressFinalize(this);
    }
}
