using Microsoft.AspNetCore.Components;
using Microsoft.JSInterop;

using SwissArmyBench.Web.Api;
using SwissArmyBench.Web.Api.Grids;
using SwissArmyBench.Web.Components;
using SwissArmyBench.Web.State;

namespace SwissArmyBench.Web.Pages.Grids;

public partial class GridsPage : IDisposable
{
    private IReadOnlyList<GridListItem> _tabs = [];
    private GridInfo? _info;
    private string? _active;
    private string? _column;
    private long? _rows;
    private bool _loaded;
    private Exception? _error;
    private AgGrid? _grid;

    [Inject]
    private GridsClient Grids { get; set; } = default!;

    [Inject]
    private LiveUpdates Live { get; set; } = default!;

    [Inject]
    private NavigationManager Nav { get; set; } = default!;

    [Inject]
    private Dialogs Dialogs { get; set; } = default!;

    [Inject]
    private IJSRuntime Js { get; set; } = default!;

    [Inject]
    private Notes Notes { get; set; } = default!;

    [Inject]
    private GridStatus Status { get; set; } = default!;

    /// <summary>The tab shown (a grid's id); none: the first.</summary>
    [SupplyParameterFromQuery(Name = "grid")]
    public string? GridParameter { get; set; }

    /// <summary>A table by its name (a Session entry's link).</summary>
    [SupplyParameterFromQuery(Name = "table")]
    public string? TableParameter { get; set; }

    [SupplyParameterFromQuery(Name = "new")]
    public string? NewParameter { get; set; }

    private bool IsNewQuery => NewParameter is not null;

    protected override void OnInitialized() => Live.NoticeArrived += OnNotice;

    protected override async Task OnParametersSetAsync()
    {
        await LoadAsync();
        await Js.InvokeVoidAsync("sab.setTitle", _info?.Title ?? "Grids");
    }

    private async Task LoadAsync()
    {
        try
        {
            _tabs = await Grids.ListAsync();
            _error = null;
        }
        catch (ApiException error)
        {
            _error = error;
        }
        _loaded = true;
        var wanted = GridParameter
            ?? _tabs.FirstOrDefault(t => t.Dataset == TableParameter)?.Grid
            ?? (_tabs.Any(t => t.Grid == _active) ? _active : _tabs.FirstOrDefault()?.Grid);
        if (wanted is null || IsNewQuery)
        {
            _info = null;
            return;
        }
        var changedTable = wanted != _active;
        if (changedTable)
        {
            _column = null;
            _rows = null;
            _selection = GridSelection.None;
            Status.Set(null);
        }
        _active = wanted;
        await ReloadInfoAsync();
        if (changedTable)
        {
            await LoadConnectionAsync();
        }
    }

    private async Task ReloadInfoAsync()
    {
        if (_active is null)
        {
            return;
        }
        try
        {
            _info = await Grids.InfoAsync(_active);
        }
        catch (ApiException error)
        {
            _error = error;
            _info = null;
        }
        StateHasChanged();
    }

    private string TypeOf(string column) => _info?.Columns.FirstOrDefault(c => c.Name == column)?.Type ?? string.Empty;

    private void ShowColumn(string column) => _column = column;

    private void Counted(long rows) => _rows = rows;

    private void RowsFailed(string words) =>
        _error = new ApiException(0, ApiClient.ReadRefusal(words, System.Net.HttpStatusCode.InternalServerError), words);

    /// <summary>A step's change: the grid's new view, its columns again and every row window asked for anew.</summary>
    private async Task ChangedAsync(Func<Task<GridInfo>> change)
    {
        try
        {
            _info = await change();
            _error = null;
            if (_grid is not null)
            {
                await _grid.RefreshAsync(_info.Columns);
            }
            if (_info.StepError is { } broken)
            {
                _ = Notes.SayAsync($"Step {broken.Index + 1}: {broken.Message}");
            }
            _tabs = await Grids.ListAsync();
        }
        catch (ApiException error)
        {
            _error = error;
        }
    }

    private Task AddStepAsync((string Kind, object Params) step) => ChangedAsync(() => Grids.AddStepAsync(_active!, step.Kind, step.Params));

    private Task ToggleStepAsync((int Index, bool Enabled) toggle) => ChangedAsync(() => Grids.ToggleStepAsync(_active!, toggle.Index, toggle.Enabled));

    private Task DeleteStepAsync(int index) => ChangedAsync(() => Grids.DeleteStepAsync(_active!, index));

    private Task UndoAsync() => ChangedAsync(() => Grids.UndoAsync(_active!));

    private Task RedoAsync() => ChangedAsync(() => Grids.RedoAsync(_active!));

    private async Task CloseTableAsync()
    {
        if (_info is not { } info)
        {
            return;
        }
        if (!await Dialogs.AskYesNoAsync($"Close {info.Dataset}?", "The table and its steps close; its rows leave the app's memory.", "Close table"))
        {
            return;
        }
        try
        {
            await Grids.CloseAsync(info.Dataset);
            _active = null;
            _info = null;
            Nav.NavigateTo("grids");
        }
        catch (ApiException error)
        {
            _error = error;
        }
    }

    private async Task MadeAsync(string grid)
    {
        await LoadAsync();
        Nav.NavigateTo($"grids?grid={Uri.EscapeDataString(grid)}");
    }

    private void OnNotice(Notice notice)
    {
        var mine = notice.Text("grid") == _active;
        if (notice.Type.StartsWith("dataset_", StringComparison.Ordinal) || notice.Type is "grid_closed" or "grid_shown")
        {
            _ = InvokeAsync(async () =>
            {
                await LoadAsync();
                StateHasChanged();
            });
        }
        else if (notice.Type == "grid_updated" && mine && notice.Text("by") != ApiClient.ClientId)
        {
            _ = InvokeAsync(async () => await ChangedAsync(() => Grids.InfoAsync(_active!)));
        }
    }

    public void Dispose()
    {
        Live.NoticeArrived -= OnNotice;
        Status.Set(null);
        GC.SuppressFinalize(this);
    }
}
