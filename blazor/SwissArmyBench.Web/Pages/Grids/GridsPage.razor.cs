using Microsoft.AspNetCore.Components;
using Microsoft.JSInterop;

using SwissArmyBench.Web.Api;
using SwissArmyBench.Web.Api.Grids;
using SwissArmyBench.Web.Components;
using SwissArmyBench.Web.Pages.Grids.Tabs;
using SwissArmyBench.Web.State;

namespace SwissArmyBench.Web.Pages.Grids;

public partial class GridsPage : IDisposable
{
    private const string OrderKey = "workspace.order";
    // The column profiles in the headers on or off (gridHeader.js keeps the same key).
    private const string ProfilesKey = "headerProfiles";

    private readonly Dictionary<string, GridInfo> _infos = [];
    private IReadOnlyList<GridListItem> _tabs = [];
    private IReadOnlyList<string> _order = [];
    private string? _active;
    private string? _goneSaid;
    private bool _loaded;
    private Exception? _error;
    private string? _variantOf;
    private GridTabs? _tabRow;
    private string? _dragging;

    [Inject]
    private GridsClient Grids { get; set; } = default!;

    [Inject]
    private ComparesClient Compares { get; set; } = default!;

    [Inject]
    private LiveUpdates Live { get; set; } = default!;

    [Inject]
    private NavigationManager Nav { get; set; } = default!;

    [Inject]
    private IJSRuntime Js { get; set; } = default!;

    [Inject]
    private Notes Notes { get; set; } = default!;

    [Inject]
    private GridStatus Status { get; set; } = default!;

    [Inject]
    private ApiClient Api { get; set; } = default!;

    /// <summary>The tab shown (a grid's id); none: the first.</summary>
    [SupplyParameterFromQuery(Name = "grid")]
    public string? GridParameter { get; set; }

    /// <summary>A table by its name (a Session entry's link).</summary>
    [SupplyParameterFromQuery(Name = "table")]
    public string? TableParameter { get; set; }

    /// <summary>An old New query address (tables?new=1): a new SQL file on the Scripts page instead.</summary>
    [SupplyParameterFromQuery(Name = "new")]
    public string? NewParameter { get; set; }

    /// <summary>The Tables list open (the status bar's memory meter links here).</summary>
    [SupplyParameterFromQuery(Name = "tables")]
    public string? TablesParameter { get; set; }

    /// <summary>Two grids side by side: "left,right".</summary>
    [SupplyParameterFromQuery(Name = "split")]
    public string? SplitParameter { get; set; }

    /// <summary>The grid in front (the ribbon acts on it): the active pane's view.</summary>
    private GridInfo? _info
    {
        get => _active is not null && _infos.TryGetValue(_active, out var info) ? info : null;
        set
        {
            if (_active is null)
            {
                return;
            }
            if (value is null)
            {
                _infos.Remove(_active);
            }
            else
            {
                _infos[_active] = value;
            }
        }
    }

    private Dictionary<string, GridPane> Panes { get; } = [];

    private bool _profilesOn;

    private AgGrid? _grid => _active is not null && Panes.TryGetValue(_active, out var pane) ? pane.Grid : null;

    /// <summary>The panes on screen: the two side by side, or the grid in front.</summary>
    private IEnumerable<GridInfo> Shown =>
        (_split ?? (_active is null ? [] : [_active]))
            .Where(_infos.ContainsKey)
            .Select(id => _infos[id]);

    protected override async Task OnInitializedAsync()
    {
        Live.NoticeArrived += OnNotice;
        OfferCommands();
        var kept = await Js.InvokeAsync<string?>("sab.recall", OrderKey);
        _profilesOn = await Js.InvokeAsync<string?>("sab.recall", ProfilesKey) == "1";
        _order = kept is { Length: > 0 } ? kept.Split(',', StringSplitOptions.RemoveEmptyEntries) : [];
        await ListenForDropsAsync();
    }

    protected override async Task OnParametersSetAsync()
    {
        if (LeftForNewQuery())
        {
            return;
        }
        await LoadAsync();
        if (TablesParameter is not null)
        {
            _dialog = TablesList;
        }
        await Js.InvokeVoidAsync("sab.setTitle", _info?.Title ?? "Tables");
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
        await SetOrderAsync(TabOrder.Normalize(_tabs, _order));
        await LoadMarksAsync();
        var open = _tabs.Select(t => t.Grid).ToHashSet();
        foreach (var gone in _infos.Keys.Where(id => !open.Contains(id)).ToList())
        {
            _infos.Remove(gone);
            Panes.Remove(gone);
        }
        var wanted = GridParameter
            ?? _tabs.FirstOrDefault(t => t.Dataset == TableParameter)?.Grid
            ?? (open.Contains(_active ?? string.Empty) ? _active : _order.FirstOrDefault());
        if (GridParameter is { } asked && !open.Contains(asked) && _error is null && _goneSaid != asked)
        {
            // A link to a grid that closed since (a Session entry, an old address): said once, as the classic does.
            _goneSaid = asked;
            _ = Notes.SayAsync("It is not open any more.");
        }
        if (wanted is null || !open.Contains(wanted))
        {
            _active = null;
            await ShowSplitAsync(null);
            return;
        }
        var changedTable = wanted != _active;
        if (changedTable)
        {
            _selection = GridSelection.None;
            Status.Set(null);
        }
        _active = wanted;
        await ReloadInfoAsync();
        await ShowSplitAsync(ReadSplit(open));
        if (changedTable)
        {
            await LoadConnectionAsync();
            _ = Api.PostAsync("/workspace/active", new { grid = wanted }).ContinueWith(_ => { }, TaskScheduler.Default);
        }
    }

    private async Task ReloadInfoAsync()
    {
        foreach (var id in (_split ?? []).Append(_active).OfType<string>().Distinct())
        {
            try
            {
                var was = _infos.GetValueOrDefault(id);
                var now = await Grids.InfoAsync(id);
                _infos[id] = now;
                // A table read again (a reload, a sandbox edit, a new version pushed): its rows are asked for anew.
                if (was is not null && was.Version != now.Version && Panes.TryGetValue(id, out var pane) && pane.Grid is { } grid)
                {
                    await grid.RefreshAsync(now.Columns);
                }
            }
            catch (ApiException error)
            {
                _error = error;
                _infos.Remove(id);
            }
        }
        StateHasChanged();
    }

    private async Task SetOrderAsync(IReadOnlyList<string> order)
    {
        _order = order;
        await Js.InvokeVoidAsync("sab.remember", OrderKey, string.Join(',', order));
    }

    private string TypeOf(string column) => _info?.Columns.FirstOrDefault(c => c.Name == column)?.Type ?? string.Empty;

    private void RowsFailed(string words) =>
        _error = new ApiException(0, ApiClient.ReadRefusal(words, System.Net.HttpStatusCode.InternalServerError), words);

    /// <summary>A step's change: the grid's new view, its columns again and every row window asked for anew.</summary>
    private async Task ChangedAsync(Func<Task<GridInfo>> change)
    {
        try
        {
            await ApplyAsync(await change());
            _error = null;
        }
        catch (ApiException error)
        {
            _error = error;
        }
    }

    /// <summary>The grid in front's new view drawn (its columns again, its rows asked for anew), the tabs' counts
    /// and a compare's counts read again.</summary>
    private async Task ApplyAsync(GridInfo info)
    {
        _info = info;
        if (_grid is not null)
        {
            await _grid.RefreshAsync(info.Columns);
        }
        if (info.StepError is { } broken)
        {
            _ = Notes.SayAsync($"Step {broken.Index + 1}: {broken.Message}");
        }
        _tabs = await Grids.ListAsync();
        await RecountCompareAsync();
    }

    private Task AddStepAsync((string Kind, object Params) step) => ChangedAsync(() => Grids.AddStepAsync(_active!, step.Kind, step.Params));

    private Task ToggleStepAsync((int Index, bool Enabled) toggle) => ChangedAsync(() => Grids.ToggleStepAsync(_active!, toggle.Index, toggle.Enabled));

    private async Task DeleteStepAsync(int index)
    {
        var words = _info?.Steps.ElementAtOrDefault(index)?.Description ?? string.Empty;
        await ChangedAsync(() => Grids.DeleteStepAsync(_active!, index));
        UndoNote($"Removed the step: {words}");
    }

    private Task UndoAsync() => ChangedAsync(() => Grids.UndoAsync(_active!));

    /// <summary>After a move that takes something away: it says so, with Undo (that grid's last step change).</summary>
    private void UndoNote(string words)
    {
        var grid = _active;
        _ = Notes.SayAsync(words, "Undo", () => grid is null ? Task.CompletedTask : InvokeAsync(() => ChangedAsync(() => Grids.UndoAsync(grid))));
    }

    public void Dispose()
    {
        Live.NoticeArrived -= OnNotice;
        WithdrawCommands();
        Status.Set(null);
        Status.SetRows(null);
        _scrollLock?.InvokeVoidAsync("release");
        _drop?.Dispose();
        _pasteListener?.InvokeVoidAsync("stop");
        GC.SuppressFinalize(this);
    }
}
