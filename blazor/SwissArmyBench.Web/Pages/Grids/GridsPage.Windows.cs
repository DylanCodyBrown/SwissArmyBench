using Microsoft.JSInterop;

namespace SwissArmyBench.Web.Pages.Grids;

/// <summary>
/// The grid page's pop-out windows (the owner's design: separate windows, so they can sit on another screen): View
/// steps, the Key Finder and the SQL window open in a window of their own (the desktop app's window.open makes an app
/// window; a browser a pop-up), each showing PanelWindow. The page hears what they change by the live notices.
/// </summary>
public partial class GridsPage
{
    // The classic windows' sizes (stepsStrip.ts, keyFinder.ts, swapConnection.ts).
    private const string StepsFeatures = "popup,width=460,height=820";
    private const string KeysFeatures = "popup,width=1100,height=760";
    private const string SqlFeatures = "popup,width=960,height=680";

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
