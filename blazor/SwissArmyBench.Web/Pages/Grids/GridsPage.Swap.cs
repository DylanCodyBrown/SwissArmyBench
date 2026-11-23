using SwissArmyBench.Web.Api;
using SwissArmyBench.Web.Api.Grids;

namespace SwissArmyBench.Web.Pages.Grids;

/// <summary>
/// A table read from another connection (the classic swapConnection.ts): the Table row's Connection: name opens the
/// chooser; a swap says so with Undo (and the steps that no longer fit); a query to look over opens its review; then
/// the code that named the old connection is offered to point at the new one.
/// </summary>
public partial class GridsPage
{
    private (string From, string To, IReadOnlyList<CodeReference> References)? _repointing;

    // Tables sent to the SQL window to run on another connection: its first swap heard offers Point these at it.
    private (string From, string To, HashSet<string> Waiting)? _reviewed;

    /// <summary>A table_connection notice from the SQL window: a table it moved to the reviewed connection.</summary>
    private void HeardSwap(SwissArmyBench.Web.State.Notice notice)
    {
        if (notice.Type != "table_connection" || _reviewed is not { } reviewed || notice.Text("dataset") is not { } table
            || !reviewed.Waiting.Contains(table) || !string.Equals(notice.Text("connection"), reviewed.To, StringComparison.OrdinalIgnoreCase))
        {
            return;
        }
        _reviewed = null;
        _ = InvokeAsync(async () =>
        {
            await OfferRepointAsync(reviewed.From, reviewed.To);
            StateHasChanged();
        });
    }

    private async Task SwappedAsync(Swapped done)
    {
        _ = Notes.SayAsync($"{done.Table}: {done.To}", "Undo", () => InvokeAsync(() => UndoSwapAsync(done.Table)));
        if (done.StepsProblems.Count > 0)
        {
            _ = Notes.SayAsync($"{done.StepsProblems.Count} steps of {done.Table} no longer fit.");
        }
        await ReloadInfoAsync();
        await LoadConnectionAsync();
        if (_grid is not null && _info is not null)
        {
            await _grid.RefreshAsync(_info.Columns);
        }
        await OfferRepointAsync(done.From, done.To);
    }

    private async Task UndoSwapAsync(string table)
    {
        try
        {
            await Grids.UndoSwapAsync(table);
            await ReloadInfoAsync();
            await LoadConnectionAsync();
        }
        catch (ApiException error)
        {
            _error = error;
        }
    }

    private Task UndoActiveSwapAsync() => _info is { } info ? UndoSwapAsync(info.Dataset) : Task.CompletedTask;

    /// <summary>The cells that named the old connection, each ticked: Point these at the new one. Shown only when
    /// there are some (`always`: said when there are none).</summary>
    private async Task OfferRepointAsync(string? from, string to, bool always = false)
    {
        if (from is null || string.Equals(from, to, StringComparison.OrdinalIgnoreCase))
        {
            return;
        }
        try
        {
            var references = (await Grids.ReferencesAsync(from)).Where(r => r.Pickable).ToList();
            if (references.Count > 0)
            {
                _repointing = (from, to, references);
            }
            else if (always)
            {
                _ = Notes.SayAsync($"No cells name {from}");
            }
        }
        catch (ApiException)
        {
            // No references to offer: nothing to do.
        }
    }
}
