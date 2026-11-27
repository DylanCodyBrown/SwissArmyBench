using Microsoft.JSInterop;

using SwissArmyBench.Web.Api;
using SwissArmyBench.Web.Api.Grids;
using SwissArmyBench.Web.Components;
using SwissArmyBench.Web.Pages.Grids.Compare;
using SwissArmyBench.Web.Pages.Grids.Tabs;

namespace SwissArmyBench.Web.Pages.Grids;

/// <summary>
/// The split and the compare (the classic panes.ts split and compare.ts). Two grids side by side, made by dropping
/// a tab on another tab (or on a half of the grid), or by a tab's Compare with…; the key picker opens as a split is
/// made. Once there are keys the two grids line up row for row (both read the same server mapping, so row N on the
/// left and row N on the right share a key, or one side shows a shaded placeholder) and scroll together. Modes:
/// outer join, anti join (one side, or both), cross compare (a row picked on one side filters the other to its key)
/// and diff (only the rows and columns that differ). The compare belongs to its two grids: any other split ends it.
/// </summary>
public partial class GridsPage
{
    private const string CompareKeys = "compare-keys";
    private const string DiffOptions = "diff-options";

    private IReadOnlyList<string>? _split;
    private GridCompare? _compare;
    private KeyGroup? _keyRows;
    private IJSObjectReference? _scrollLock;
    private bool _lockWanted;

    /// <summary>The two grids side by side (left, right) with their views, or null.</summary>
    private (GridInfo Left, GridInfo Right)? SplitPair =>
        _split is [var left, var right] && _infos.TryGetValue(left, out var l) && _infos.TryGetValue(right, out var r) ? (l, r) : null;

    /// <summary>Aligned grids (every mode but cross compare) keep one vertical position.</summary>
    private bool Aligned => _compare is { Mode: not "cross" };

    private CompareView? CompareOf(string grid) => _compare switch
    {
        null => null,
        { Left: var left } c when left == grid => new CompareView(c.Compare, "left"),
        { Right: var right } c when right == grid => new CompareView(c.Compare, "right"),
        _ => null,
    };

    /// <summary>Diff mode with Only differing columns: each side's keys and its columns that differ.</summary>
    private IReadOnlyList<string>? OnlyOf(string grid) => _compare is { Mode: "diff", Diff.OnlyDiffering: true, Differ: { } differ } c
        ? grid == c.Left ? differ.Shown.Left : grid == c.Right ? differ.Shown.Right : null
        : null;

    private CompareFocus? FocusOn(string grid) => _compare?.Focus is { } focus && CompareOf(grid)?.Side == focus.Side ? focus : null;

    protected override async Task OnAfterRenderAsync(bool firstRender)
    {
        Screen.Touch();
        // The two aligned grids are locked together once both are drawn (a render or two after the split).
        if (_lockWanted && _scrollLock is null && SplitPair is { } pair && Panes.TryGetValue(pair.Left.Grid, out var left) && Panes.TryGetValue(pair.Right.Grid, out var right)
            && left.Grid is { } a && right.Grid is { } b)
        {
            _scrollLock = await a.LockScrollAsync(b);
        }
    }

    /// <summary>The address's split, when both its grids are still open and the one in front is one of them.</summary>
    private IReadOnlyList<string>? ReadSplit(HashSet<string> open)
    {
        var pair = SplitParameter?.Split(',');
        return pair is [var left, var right] && left != right && open.Contains(left) && open.Contains(right) && (left == _active || right == _active)
            ? [left, right]
            : null;
    }

    /// <summary>The split shown (or none): a compare on another pair ends; a compare running on this pair is taken
    /// up (a reload, the Key Finder's or the agent's compare).</summary>
    private async Task ShowSplitAsync(IReadOnlyList<string>? split)
    {
        var was = _split;
        _split = split;
        foreach (var id in split ?? [])
        {
            if (!_infos.ContainsKey(id))
            {
                await LoadInfoAsync(id);
            }
        }
        if (_compare is { } cmp && (split is null || split[0] != cmp.Left || split[1] != cmp.Right))
        {
            await StopCompareAsync();
        }
        if (split is not null && _compare is null && !SameSplit(was, split))
        {
            var running = await RunningCompareAsync(split);
            if (running is not null)
            {
                await UseCompareAsync(running);
            }
        }
        if (split is null)
        {
            await ReleaseLockAsync();
        }
    }

    private static bool SameSplit(IReadOnlyList<string>? a, IReadOnlyList<string>? b) => a is not null && b is not null && a.SequenceEqual(b);

    private async Task<GridCompare?> RunningCompareAsync(IReadOnlyList<string> split)
    {
        try
        {
            return (await Compares.RunningAsync()).FirstOrDefault(c => c.Left == split[0] && c.Right == split[1]);
        }
        catch (ApiException)
        {
            return null;
        }
    }

    private async Task LoadInfoAsync(string grid)
    {
        try
        {
            _infos[grid] = await Grids.InfoAsync(grid);
        }
        catch (ApiException error)
        {
            _error = error;
        }
    }

    /// <summary>`dragged` beside `beside` (on the right), the key picker opened: a tab dropped on a tab.</summary>
    private Task SplitWithAsync((string Dragged, string Beside) drop) => SplitAsync(drop.Dragged, drop.Beside, "right", pickKeys: true);

    /// <summary>A tab dropped on a half of the grid: that half is the dragged grid's.</summary>
    private Task DropOnGridAsync(string dragged, string side)
    {
        _dragging = null;
        return _active is { } active ? SplitAsync(dragged, active, side, pickKeys: true) : Task.CompletedTask;
    }

    private async Task SplitAsync(string dragged, string beside, string side, bool pickKeys)
    {
        if (dragged == beside)
        {
            return;
        }
        IReadOnlyList<string> pair = side == "left" ? [dragged, beside] : [beside, dragged];
        Nav.NavigateTo(Address(dragged, pair));
        await Task.Yield();
        if (pickKeys && (await RunningCompareAsync(pair)) is null)
        {
            _dialog = CompareKeys;
            StateHasChanged();
        }
    }

    /// <summary>Close this side: back to one grid (`keep` stays; the other stays open as a tab).</summary>
    private Task UnsplitAsync(string closing)
    {
        var keep = _split?.FirstOrDefault(g => g != closing) ?? closing;
        Nav.NavigateTo(Address(keep, null));
        return Task.CompletedTask;
    }

    /// <summary>A tab's right-click menu: Compare with…, Rename, Collaborate (the panel on its table's threads), Close.</summary>
    private void TabMenu((string Grid, double X, double Y) at)
    {
        var tab = _tabs.FirstOrDefault(t => t.Grid == at.Grid);
        if (tab is null)
        {
            return;
        }
        var label = TabOrder.Label(tab, _tabs, _order);
        _menu = new OpenMenu(label,
        [
            new("Compare with…", "columns", () => CompareWithAsync(at.Grid, at.X, at.Y), _tabs.Count < 2 ? "Open another table to compare with" : null),
            new("Rename", "rename", () => _tabRow?.StartRenameAsync(at.Grid) ?? Task.CompletedTask),
            Collaboration.Entry(new("table", tab.Dataset, string.Empty, tab.Dataset)),
            MenuEntry.Separator,
            new("Close", "close", () => CloseGridAsync(at.Grid)),
        ], at.X, at.Y);
    }

    /// <summary>Compare with…: another open table beside this one (which stays on the left). One other table: that
    /// one at once; several: a list of them.</summary>
    private Task CompareWithAsync(string grid, double x, double y)
    {
        var others = _order.Where(g => g != grid).ToList();
        if (others.Count == 1)
        {
            return SplitAsync(others[0], grid, "right", pickKeys: true);
        }
        if (others.Count == 0)
        {
            return Task.CompletedTask;
        }
        var tab = _tabs.First(t => t.Grid == grid);
        _menu = new OpenMenu($"Compare {TabOrder.Label(tab, _tabs, _order)} with",
            others
                .Select(o => _tabs.First(t => t.Grid == o))
                .Select(o => new MenuEntry(TabOrder.Label(o, _tabs, _order), "columns", () => SplitAsync(o.Grid, grid, "right", pickKeys: true)))
                .ToList(), x, y);
        return Task.CompletedTask;
    }

    private async Task StartCompareAsync(IReadOnlyList<IReadOnlyList<string>> keys)
    {
        _dialog = null;
        if (SplitPair is not { } pair)
        {
            return;
        }
        if (_compare is not null)
        {
            await StopCompareAsync();
        }
        try
        {
            var started = await Compares.StartAsync(pair.Left.Grid, pair.Right.Grid, keys);
            await UseCompareAsync(started);
            var c = started.Counts;
            _ = Notes.SayAsync($"Aligned on {started.KeyWords}: {c.Matched:N0} matched, {c.LeftOnly:N0} left only, {c.RightOnly:N0} right only.");
        }
        catch (ApiException error)
        {
            _error = error;
        }
    }

    /// <summary>The compare drawn: both panes read its rows, aligned grids locked together, diff mode at the first
    /// column that differs.</summary>
    private async Task UseCompareAsync(GridCompare compare)
    {
        var jump = _compare?.Mode != compare.Mode || _compare?.Diff.Column != compare.Diff.Column;
        _compare = compare;
        _keyRows = null;
        if (Aligned)
        {
            _lockWanted = true;
        }
        else
        {
            await ReleaseLockAsync();
        }
        StateHasChanged();
        if (jump && compare is { Mode: "diff", Differ: { } differ })
        {
            await Task.Yield();
            var focused = compare.Diff.Column;
            var to = focused is not null ? new CompareFirst(focused, focused) : differ.First;
            if (to is not null)
            {
                await (Pane(compare.Left)?.RevealColumnAsync(to.Left) ?? Task.CompletedTask);
                await (Pane(compare.Right)?.RevealColumnAsync(to.Right) ?? Task.CompletedTask);
            }
        }
    }

    private AgGrid? Pane(string grid) => Panes.TryGetValue(grid, out var pane) ? pane.Grid : null;

    private async Task ChangeCompareAsync(object patch)
    {
        if (_compare is not { } cmp)
        {
            return;
        }
        try
        {
            await UseCompareAsync(await Compares.ChangeAsync(cmp.Compare, patch));
        }
        catch (ApiException error)
        {
            _error = error;
        }
    }

    private Task ApplyDiffOptionsAsync(CompareDiffOptions options) => ChangeCompareAsync(new { diff = CompareRow.Options(options) });

    private async Task StopCompareAsync()
    {
        var was = _compare;
        _compare = null;
        _keyRows = null;
        await ReleaseLockAsync();
        if (was is not null)
        {
            try
            {
                await Compares.StopAsync(was.Compare);
            }
            catch (ApiException)
            {
                // Stopped already (the agent, a restart): nothing more to do.
            }
        }
    }

    private async Task ReleaseLockAsync()
    {
        _lockWanted = false;
        if (_scrollLock is not null)
        {
            await _scrollLock.InvokeVoidAsync("release");
            await _scrollLock.DisposeAsync();
            _scrollLock = null;
        }
    }

    /// <summary>A step on either side changes what lines up: the counts are read again.</summary>
    private async Task RecountCompareAsync()
    {
        if (_compare is not { } cmp)
        {
            return;
        }
        try
        {
            var now = await Compares.ReadAsync(cmp.Compare);
            _compare = now with { Focus = cmp.Focus };
        }
        catch (ApiException)
        {
            _compare = null;
        }
    }

    /// <summary>A compared row clicked: aligned, every row sharing its key lights up on both sides; cross compare,
    /// the other side is filtered to its key.</summary>
    private async Task RowPickedAsync(string grid, long row)
    {
        if (_compare is not { } cmp || CompareOf(grid) is not { } side)
        {
            return;
        }
        try
        {
            if (cmp.Mode == "cross")
            {
                await UseCompareAsync(await Compares.FocusAsync(cmp.Compare, side.Side, row));
            }
            else
            {
                _keyRows = await Compares.KeyGroupAsync(cmp.Compare, row);
            }
        }
        catch (ApiException error)
        {
            _error = error;
        }
    }

    private async Task ClearFocusAsync()
    {
        if (_compare is { } cmp)
        {
            await UseCompareAsync(await Compares.ClearFocusAsync(cmp.Compare));
        }
    }

    /// <summary>A compare started away from this page (the Key Finder's Compare on these, the agent's): the two grids
    /// side by side, lined up. No key picker.</summary>
    private async Task ShowCompareAsync(string compare)
    {
        try
        {
            var found = await Compares.ReadAsync(compare);
            if (!_tabs.Any(t => t.Grid == found.Left) || !_tabs.Any(t => t.Grid == found.Right))
            {
                return;
            }
            Nav.NavigateTo(Address(found.Right, [found.Left, found.Right]));
        }
        catch (ApiException)
        {
            // Stopped again already.
        }
    }
}
