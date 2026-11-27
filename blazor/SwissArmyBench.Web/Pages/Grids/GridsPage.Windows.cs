using Microsoft.AspNetCore.Components;
using Microsoft.JSInterop;

using SwissArmyBench.Web.Api.App;
using SwissArmyBench.Web.Api.Grids;
using SwissArmyBench.Web.Components;
using SwissArmyBench.Web.Pages.Grids.Tabs;
using SwissArmyBench.Web.State;

namespace SwissArmyBench.Web.Pages.Grids;

/// <summary>
/// The grid page's pop-out windows (the owner's design: separate windows, so they can sit on another screen): View
/// steps, the Key Finder and the SQL window open in a window of their own (the desktop app's window.open makes an app
/// window; a browser a pop-up), each showing PanelWindow. The page hears what they change by the live notices.
/// A table itself pops out by the app's one mechanism (State/PopOuts.cs; the owner, 2026-11-27): its own window shows
/// the Tables page on that table alone, and its pane here is blank but for Reattach and Show window.
/// </summary>
public partial class GridsPage
{
    // The classic windows' sizes (stepsStrip.ts, keyFinder.ts, swapConnection.ts).
    private const string StepsFeatures = "popup,width=460,height=820";
    private const string KeysFeatures = "popup,width=1100,height=760";
    private const string SqlFeatures = "popup,width=960,height=680";

    [Inject]
    private PopOuts PopOuts { get; set; } = default!;

    /// <summary>The tab row's tabs: every open table, or, in a table's own window, that table alone.</summary>
    private IReadOnlyList<GridListItem> TabsShown =>
        OwnGrid is { } own ? _tabs.Where(t => t.Grid == own).ToList() : _tabs;

    /// <summary>The table this window holds as its own window (null in a main window and a page's window).</summary>
    private string? OwnGrid =>
        PopOuts.Own is { } key && key.StartsWith($"{PopOutKeys.Table}:", StringComparison.Ordinal) ? key[(PopOutKeys.Table.Length + 1)..] : null;

    /// <summary>The table's entry when it is live in a window of its own, not this one.</summary>
    private PopOutEntry? PoppedOut(string grid) => PopOuts.Elsewhere(PopOutKeys.TableKey(grid));

    private Task PopOutAsync(string grid) =>
        _tabs.FirstOrDefault(t => t.Grid == grid) is { } tab
            ? PopOuts.PopAsync(PopOutKeys.TableKey(grid), TabOrder.Label(tab, _tabs, _order), Address(grid, null))
            : Task.CompletedTask;

    /// <summary>A tab's menu: Pop out, or, while it is in its own window, Reattach and Show window.</summary>
    private IEnumerable<MenuEntry> PopOutEntries(string grid)
    {
        if (PopOuts.Own is not null)
        {
            return [];
        }
        var key = PopOutKeys.TableKey(grid);
        return PoppedOut(grid) is null
            ? [new("Pop out", "popout", () => PopOutAsync(grid))]
            : [new("Reattach", "popin", () => PopOuts.ReattachAsync(key)), new("Show window", "popout", () => PopOuts.ShowAsync(key))];
    }

    // What is popped out changed: a pane that left takes its grid with it; a table closed here leaves its window.
    private void PopOutsChanged()
    {
        foreach (var gone in Panes.Keys.Where(grid => PoppedOut(grid) is not null).ToList())
        {
            Panes.Remove(gone);
        }
        if (_active is { } front && PoppedOut(front) is not null)
        {
            Status.SetRows(null); // its rows are its own window's to count
        }
        _ = InvokeAsync(StateHasChanged);
    }

    private Task OpenStepsWindowAsync() => _info is { } info
        ? OpenWindowAsync(PanelWindow.Address(PanelWindow.Steps, info.Grid), $"steps-{info.Grid}", StepsFeatures, "The browser blocked the steps window.")
        : Task.CompletedTask;

    private Task OpenKeyFinderWindowAsync() => _info is { } info
        ? OpenWindowAsync(PanelWindow.Address(PanelWindow.Keys, info.Grid), $"keys-{info.Grid}", KeysFeatures, "The browser blocked the Key Finder window: allow pop-ups for this address.")
        : Task.CompletedTask;

    /// <summary>The SQL window: each table's query looked over, then run on the other connection.</summary>
    private void Review((string To, IReadOnlyList<string> Tables, string? Sql) review)
    {
        // The window's runs come back as the live notices (table_connection): the first one offers the code to point.
        if (_connection?.Connection is { } from)
        {
            _reviewed = (from, review.To, [.. review.Tables]);
        }
        _ = OpenWindowAsync(PanelWindow.SqlAddress(review.To, review.Tables, review.Sql), "sab-connsql", SqlFeatures, "The browser blocked the SQL window: allow pop-ups for this address.");
    }

    private async Task OpenWindowAsync(string address, string name, string features, string blocked)
    {
        _dialog = null;
        var opened = await Js.InvokeAsync<IJSObjectReference?>("open", address, name, features);
        if (opened is null)
        {
            _error = new InvalidOperationException(blocked);
            StateHasChanged();
            return;
        }
        await opened.InvokeVoidAsync("focus");
        await opened.DisposeAsync();
    }
}
