using Microsoft.AspNetCore.Components;
using Microsoft.JSInterop;

using SwissArmyBench.Web.Api;
using SwissArmyBench.Web.Api.Analyze;
using SwissArmyBench.Web.State;

namespace SwissArmyBench.Web.Pages.Analyze;

public partial class AnalyzePage
{
    private AnalyzeToolbar? _toolbar;
    private IReadOnlyList<BoardCard> _cards = [];
    private HashSet<string> _fresh = [];
    private string? _analysis;
    private RunInputs? _again;
    private Exception? _error;

    [Inject]
    private AnalyzeClient AnalyzeApi { get; set; } = default!;

    [Inject]
    private LiveUpdates Live { get; set; } = default!;

    [Inject]
    private IJSRuntime Js { get; set; } = default!;

    /// <summary>The analysis an address names (analyze?analysis=odds&amp;table=g1: the palette's Analyze entries), its
    /// form opened on arrival.</summary>
    [SupplyParameterFromQuery(Name = "analysis")]
    public string? AnalysisParameter { get; set; }

    /// <summary>The table an address names for that analysis (a grid's id).</summary>
    [SupplyParameterFromQuery(Name = "table")]
    public string? TableParameter { get; set; }

    private string? _addressTaken;

    // An analysis named in the address preselects the toolbar's, once per address (a later pick on the page stands).
    protected override void OnParametersSet()
    {
        var address = $"{AnalysisParameter}|{TableParameter}";
        if (AnalysisParameter is { Length: > 0 } named && address != _addressTaken)
        {
            _addressTaken = address;
            Choose(named);
        }
    }

    /// <summary>The toolbar's analyses by their group, in the server's order (everyday words first).</summary>
    private IEnumerable<IGrouping<string, AnalysisEntry>> Groups =>
        (_toolbar?.Analyses ?? [])
            .GroupBy(a => a.Group)
            .OrderBy(g => (_toolbar?.Groups ?? []).ToList().IndexOf(g.Key));

    protected override async Task OnInitializedAsync()
    {
        Live.NoticeArrived += OnNotice;
        await Js.InvokeVoidAsync("sab.setTitle", "Analyze");
        await LoadAsync();
    }

    private async Task LoadAsync()
    {
        try
        {
            _toolbar = await AnalyzeApi.ToolbarAsync(null);
            await LoadCardsAsync();
            _error = null;
        }
        catch (ApiException error)
        {
            _error = error;
        }
    }

    /// <summary>The board's cards in their order on the board (an analysis's land at its top).</summary>
    private async Task LoadCardsAsync()
    {
        _cards = (await AnalyzeApi.CardsAsync()).Cards
            .OrderBy(c => c.Order)
            .ThenByDescending(c => c.Created)
            .ToList();
    }

    private void Choose(string analysis)
    {
        _analysis = analysis;
        _again = null;
    }

    private async Task RanAsync(AnalyzeRun ran)
    {
        _fresh = [.. ran.Cards];
        await LoadCardsAsync();
        _toolbar = await AnalyzeApi.ToolbarAsync(null);
    }

    private async Task RemoveAsync(BoardCard card)
    {
        try
        {
            await AnalyzeApi.DeleteCardAsync(card.Id);
            await LoadCardsAsync();
        }
        catch (ApiException error)
        {
            _error = error;
        }
    }

    /// <summary>Run again: the form opens on what the run ran with.</summary>
    private async Task AgainAsync(string run)
    {
        try
        {
            _again = await AnalyzeApi.InputsAsync(run);
            _analysis = _again.Analysis;
        }
        catch (ApiException error)
        {
            _error = error;
        }
    }

    private void OnNotice(Notice notice)
    {
        if (notice.Type == "cards_updated")
        {
            _ = InvokeAsync(async () =>
            {
                await LoadCardsAsync();
                StateHasChanged();
            });
        }
    }

    public void Dispose() => Live.NoticeArrived -= OnNotice;
}
