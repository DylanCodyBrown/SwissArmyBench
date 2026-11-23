using Microsoft.AspNetCore.Components;
using Microsoft.AspNetCore.Components.Web;
using Microsoft.JSInterop;

using SwissArmyBench.Web.Api.Grids;

namespace SwissArmyBench.Web.Pages.Grids.Tabs;

public partial class GridTabs
{
    private const string CollapsedKey = "workspace.collapsedGroups";

    private readonly HashSet<string> _collapsed = [];
    private string? _dragging;
    private string? _draggingGroup;
    private string? _dropSplit;
    private string? _renaming;
    private string? _renamed;
    private bool _renameDone;

    [Inject]
    private IJSRuntime Js { get; set; } = default!;

    [Parameter, EditorRequired]
    public IReadOnlyList<GridListItem> Tabs { get; set; } = [];

    /// <summary>The grids' ids in the row's order (TabOrder.Normalize).</summary>
    [Parameter, EditorRequired]
    public IReadOnlyList<string> Order { get; set; } = [];

    [Parameter]
    public string? Active { get; set; }

    /// <summary>The two grids side by side, left then right (null: one grid).</summary>
    [Parameter]
    public IReadOnlyList<string>? Split { get; set; }

    [Parameter]
    public bool IsNewQuery { get; set; }

    /// <summary>Buttons after the tabs (Open file…, Tables).</summary>
    [Parameter]
    public RenderFragment? Extra { get; set; }

    [Parameter]
    public EventCallback<string> OnActivate { get; set; }

    [Parameter]
    public EventCallback<string> OnClose { get; set; }

    /// <summary>A tab's right-click (or the menu key): its grid and where.</summary>
    [Parameter]
    public EventCallback<(string Grid, double X, double Y)> OnMenu { get; set; }

    /// <summary>A tab dropped on another (Dragged goes beside it, on the right).</summary>
    [Parameter]
    public EventCallback<(string Dragged, string Beside)> OnSplit { get; set; }

    /// <summary>The row's new order, after a tab or a group was moved.</summary>
    [Parameter]
    public EventCallback<IReadOnlyList<string>> OnOrder { get; set; }

    /// <summary>A tab is being dragged (its grid) or the drag ended (null): the grid offers its halves to drop on.</summary>
    [Parameter]
    public EventCallback<string?> OnDragging { get; set; }

    /// <summary>A table renamed in place: its name and the new one.</summary>
    [Parameter]
    public EventCallback<(string Dataset, string To)> OnRename { get; set; }

    private IReadOnlyList<TabGroup> Groups => TabOrder.Groups(Tabs, Order);

    protected override async Task OnInitializedAsync()
    {
        var kept = await Js.InvokeAsync<string?>("sab.recall", CollapsedKey);
        if (kept is { Length: > 0 })
        {
            _collapsed.UnionWith(kept.Split('\n', StringSplitOptions.RemoveEmptyEntries));
        }
    }

    /// <summary>Rename the grid's table in its tab (the menu's Rename, F2, the palette's).</summary>
    public async Task StartRenameAsync(string grid)
    {
        _renaming = grid;
        _renamed = null;
        _renameDone = false;
        StateHasChanged();
        await Task.Yield();
        await Js.InvokeVoidAsync("sab.focusSelect", ".tab-rename");
    }

    private async Task ClickAsync(MouseEventArgs e, GridListItem tab)
    {
        // The second click of a double-click on the name renames.
        if (e.Detail == 2)
        {
            await StartRenameAsync(tab.Grid);
            return;
        }
        await OnActivate.InvokeAsync(tab.Grid);
    }

    private async Task AuxAsync(MouseEventArgs e, GridListItem tab)
    {
        if (e.Button == 1)
        {
            await OnClose.InvokeAsync(tab.Grid);
        }
    }

    private async Task KeyAsync(KeyboardEventArgs e, GridListItem tab)
    {
        var at = Order.ToList().IndexOf(tab.Grid);
        int? to = e.Key switch
        {
            "ArrowRight" => at + 1,
            "ArrowLeft" => at - 1,
            "Home" => 0,
            "End" => Order.Count - 1,
            _ => null,
        };
        if (to is { } next && Order.Count > 0)
        {
            var grid = Order[(next + Order.Count) % Order.Count];
            await OnActivate.InvokeAsync(grid);
            await Js.InvokeVoidAsync("sab.focus", $".grid-tab[data-grid='{grid}']");
            return;
        }
        switch (e.Key)
        {
            case "Enter" or " ":
                await OnActivate.InvokeAsync(tab.Grid);
                break;
            case "Delete":
                await OnClose.InvokeAsync(tab.Grid);
                break;
            case "F2":
                await StartRenameAsync(tab.Grid);
                break;
            case "ContextMenu" when e.ShiftKey is false:
                await OnMenu.InvokeAsync((tab.Grid, 0, 0));
                break;
            default:
                break;
        }
    }

    private async Task RenameKeyAsync(KeyboardEventArgs e, GridListItem tab)
    {
        if (e.Key == "Enter")
        {
            await FinishRenameAsync(tab, true);
        }
        else if (e.Key == "Escape")
        {
            await FinishRenameAsync(tab, false);
        }
    }

    private async Task FinishRenameAsync(GridListItem tab, bool keep)
    {
        if (_renameDone)
        {
            return;
        }
        _renameDone = true;
        _renaming = null;
        var to = _renamed?.Trim();
        if (keep && to is { Length: > 0 } && to != tab.Dataset)
        {
            await OnRename.InvokeAsync((tab.Dataset, to));
        }
    }

    private async Task ToggleGroupAsync(string key)
    {
        if (!_collapsed.Remove(key))
        {
            _collapsed.Add(key);
        }
        await Js.InvokeVoidAsync("sab.remember", CollapsedKey, string.Join('\n', _collapsed));
    }

    private void DragStarted(string grid)
    {
        _dragging = grid;
        _ = OnDragging.InvokeAsync(grid);
    }

    private void DragEnded()
    {
        _dragging = null;
        _draggingGroup = null;
        _dropSplit = null;
        _ = OnDragging.InvokeAsync(null);
    }

    private async Task DropOnTabAsync(string grid)
    {
        var dragged = _dragging;
        DragEnded();
        if (dragged is not null && dragged != grid)
        {
            await OnSplit.InvokeAsync((dragged, grid));
        }
    }

    private async Task DropBeforeAsync(string grid)
    {
        var dragged = _dragging;
        var group = _draggingGroup;
        DragEnded();
        if (group is not null)
        {
            await OnOrder.InvokeAsync(TabOrder.MoveGroup(Order, Tabs, group, grid));
        }
        else if (dragged is not null)
        {
            await OnOrder.InvokeAsync(TabOrder.Normalize(Tabs, TabOrder.Move(Order, dragged, grid)));
        }
    }

    private Task DropOnGroupAsync(TabGroup group) => DropBeforeAsync(group.Tabs[0].Grid);

    private async Task DropAtEndAsync()
    {
        var dragged = _dragging;
        var group = _draggingGroup;
        DragEnded();
        if (group is not null)
        {
            await OnOrder.InvokeAsync(TabOrder.MoveGroup(Order, Tabs, group, null));
        }
        else if (dragged is not null)
        {
            await OnOrder.InvokeAsync(TabOrder.Normalize(Tabs, TabOrder.Move(Order, dragged, null)));
        }
    }
}
