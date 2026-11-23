using Microsoft.JSInterop;

namespace SwissArmyBench.Web.Pages.Analyze;

// The panel's own buttons (the classic aiPanel.ts render's header): dock the form beside the board or below it,
// maximize the board (the toolbar and form put away) or restore it, and collapse the page to its name; each
// remembered on this computer as the classic panel's layout is.
public partial class AnalyzePage
{
    // The toolbar's What can I do with a column? (not an analysis of its own: each column's analyses).
    private const string ColumnsMode = "columns";

    private string? _revealing;
    private string _dock = "right";
    private string _panel = "open";

    private string DockWords => _dock == "bottom" ? "Dock the panel to the right" : "Dock the panel below the grid";

    private string MaxWords => _panel == "max" ? "Restore the panel" : "Maximize the panel";

    private string CollapseWords => _panel == "collapsed" ? "Open the analysis panel" : "Collapse the panel";

    private string CollapseIcon => _panel == "collapsed"
        ? (_dock == "bottom" ? "up" : "collapse")
        : (_dock == "bottom" ? "down" : "expand");

    private async Task RecallPanelAsync()
    {
        _dock = await Js.InvokeAsync<string?>("sab.recall", "analyze.dock") == "bottom" ? "bottom" : "right";
        _panel = await Js.InvokeAsync<string?>("sab.recall", "analyze.panel") is ("max" or "collapsed") and var kept ? kept : "open";
    }

    private async Task DockAsync()
    {
        _dock = _dock == "bottom" ? "right" : "bottom";
        await Js.InvokeVoidAsync("sab.remember", "analyze.dock", _dock);
    }

    private async Task PanelAsync(string panel)
    {
        _panel = panel;
        await Js.InvokeVoidAsync("sab.remember", "analyze.panel", panel);
    }

    /// <summary>A note's Show (analyze?card=): that card brought into view and marked.</summary>
    [Microsoft.AspNetCore.Components.SupplyParameterFromQuery(Name = "card")]
    public string? CardToShow { get; set; }

    protected override void OnParametersSet()
    {
        if (CardToShow is { Length: > 0 } card)
        {
            (_revealing, _fresh) = (card, [card]);
        }
    }

    protected override async Task OnAfterRenderAsync(bool firstRender)
    {
        if (_revealing is { } card && _cards.Any(c => c.Id == card))
        {
            _revealing = null;
            var board = await Js.InvokeAsync<IJSObjectReference>("import", "./js/board.js");
            await board.InvokeAsync<bool>("reveal", _board, card);
        }
    }
}
