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

    [Inject]
    private IJSRuntime Js { get; set; } = default!;

    /// <summary>The server's grid id.</summary>
    [Parameter, EditorRequired]
    public string GridId { get; set; } = string.Empty;

    [Parameter, EditorRequired]
    public IReadOnlyList<GridColumn> Columns { get; set; } = [];

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

    /// <summary>Words the grid has for the user (Ctrl+C's "Copied 4 rows × 2 columns.").</summary>
    [Parameter]
    public EventCallback<string> OnSaid { get; set; }

    protected override async Task OnAfterRenderAsync(bool firstRender)
    {
        if (_mounted == GridId)
        {
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
    }

    /// <summary>The grid's steps changed: its columns again, every row asked for anew, the selection cleared.</summary>
    public async Task RefreshAsync(IReadOnlyList<GridColumn> columns)
    {
        if (_grid is not null)
        {
            await _grid.InvokeVoidAsync("refresh", columns);
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

    /// <summary>The selection on the clipboard (plain, headers or markdown); the words to say, or null.</summary>
    public async Task<string?> CopyAsync(string style) => _grid is null ? null : await _grid.InvokeAsync<string?>("copy", style);

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
