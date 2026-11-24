using SwissArmyBench.Web.Api;

namespace SwissArmyBench.Web.Pages.Grids;

/// <summary>What the tab row does (the classic panes.ts): a tab brought to the front (while split, it takes the
/// active side), a pane clicked, a grid closed with Undo, a table renamed in place; and the status bar's rows.</summary>
public partial class GridsPage
{
    /// <summary>A tab clicked (or Enter on it): it comes to the front; while split it takes the active side.</summary>
    private Task ActivateAsync(string grid)
    {
        var split = _split is { } pair && !pair.Contains(grid) && _active is { } active
            ? pair.Select(g => g == active ? grid : g).ToList()
            : _split;
        Nav.NavigateTo(Address(grid, split));
        return Task.CompletedTask;
    }

    private static string Address(string grid, IReadOnlyList<string>? split) =>
        split is [var left, var right]
            ? $"tables?grid={Uri.EscapeDataString(grid)}&split={Uri.EscapeDataString(left)},{Uri.EscapeDataString(right)}"
            : $"tables?grid={Uri.EscapeDataString(grid)}";

    /// <summary>A pane clicked: it becomes the one in front (the address follows, with no history entry).</summary>
    private Task FocusPaneAsync(string grid)
    {
        Nav.NavigateTo(Address(grid, _split), replace: true);
        return Task.CompletedTask;
    }

    /// <summary>A tab's ×, the middle button, Delete, the menu's Close: the grid closes; Undo reopens it.</summary>
    private async Task CloseGridAsync(string grid)
    {
        var name = _tabs.FirstOrDefault(t => t.Grid == grid)?.Dataset;
        try
        {
            await Api.DeleteAsync($"/grids/{ApiClient.Part(grid)}");
            if (name is not null)
            {
                _ = Notes.SayAsync($"Closed {name}", "Undo", ReopenAsync);
            }
        }
        catch (ApiException error) when (error.Status != 404)
        {
            _error = error;
        }
        var at = _order.ToList().IndexOf(grid);
        var other = _split?.FirstOrDefault(g => g != grid && (_split?.Contains(grid) ?? false));
        _infos.Remove(grid);
        _tabs = _tabs.Where(t => t.Grid != grid).ToList();
        await SetOrderAsync(_order.Where(g => g != grid).ToList());
        if (_active == grid || other is not null)
        {
            var next = other ?? _order.ElementAtOrDefault(Math.Min(at, _order.Count - 1));
            Nav.NavigateTo(next is null ? "tables" : Address(next, null), replace: true);
        }
    }

    private async Task ReopenAsync()
    {
        try
        {
            await Api.PostAsync("/grids/reopen");
        }
        catch (ApiException error) when (error.Status == 404)
        {
            _ = Notes.SayAsync("No closed table to reopen.");
        }
        catch (ApiException error)
        {
            Notes.Error(error);
        }
    }

    private async Task RenameAsync((string Dataset, string To) rename)
    {
        try
        {
            await Api.PostAsync($"/datasets/{ApiClient.Part(rename.Dataset)}/rename", new { to = rename.To });
        }
        catch (ApiException error)
        {
            _error = error;
        }
    }

    private long _total;
    private (long First, long Last) _onScreen;

    /// <summary>A pane's rows counted: the status bar says the active pane's.</summary>
    private void Counted(string grid, long rows)
    {
        if (grid == _active)
        {
            _total = rows;
            SayRows();
        }
    }

    private void ShownRows(string grid, (long First, long Last) rows)
    {
        if (grid == _active)
        {
            _onScreen = rows;
            SayRows();
        }
    }

    /// <summary>The status bar's "Rows 1–22 of 83 (120 in orders)" (the classic bottomBar.ts).</summary>
    private void SayRows()
    {
        if (_info is not { } info)
        {
            Status.SetRows(null);
            return;
        }
        var inTable = _total != info.RowCount ? $" ({info.RowCount:N0} in {info.Dataset})" : string.Empty;
        Status.SetRows(_total > 0
            ? $"Rows {Math.Min(_onScreen.First + 1, _total):N0}–{Math.Min(_onScreen.Last + 1, _total):N0} of {_total:N0}{inTable}"
            : $"0 rows ({info.RowCount:N0} in {info.Dataset})");
    }
}
