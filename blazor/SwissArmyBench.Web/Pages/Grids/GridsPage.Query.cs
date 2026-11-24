using SwissArmyBench.Web.Api.Grids;
using SwissArmyBench.Web.Pages.Grids.Query;

namespace SwissArmyBench.Web.Pages.Grids;

/// <summary>
/// A new table from a query (the classic queryTab.ts): the New query page's choice opens the draft (its tray over a
/// blank grid, a tab of its own until it is built); Run builds the table, whose tab keeps the tray so its query can
/// change and run again.
/// </summary>
public partial class GridsPage
{
    private int _drafts;

    /// <summary>The draft's name: query, query_2… (never an open table's).</summary>
    private string DraftName => Enumerable.Range(2, 1000).Select(n => $"query_{n}").Prepend("query").First(n => _tabs.All(t => t.Dataset != n));

    private IReadOnlyList<string> OpenTableNames => _order.Select(id => _tabs.FirstOrDefault(t => t.Grid == id)?.Dataset).OfType<string>().Distinct().ToList();

    private void OpenDraft(string from)
    {
        _drafts++;
        Nav.NavigateTo($"tables?new=1&from={Uri.EscapeDataString(from)}");
    }

    private void CloseDraft() => Nav.NavigateTo(_active is { } active ? Address(active, _split) : "tables?new=1");

    private async Task DraftBuiltAsync(BuiltTable built)
    {
        _ = Notes.SayAsync($"Built {built.Dataset}: {QueryTray.Rows(built.Rows)}{(built.Connection is { } on ? $" from {on}" : string.Empty)}.");
        await LoadAsync();
        Nav.NavigateTo(Address(built.Grid, null));
    }

    /// <summary>Run again: the table rebuilt in place (its tab's steps apply to the new rows).</summary>
    private Task RebuiltAsync(BuiltTable built) => ReloadInfoAsync();
}
