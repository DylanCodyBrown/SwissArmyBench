using System.Text.Json;

using SwissArmyBench.Web.Api.Grids;

namespace SwissArmyBench.Web.Api.Analyze;

/// <summary>
/// The Analyze page (routes_analyze.py, routes_cards.py): the toolbar, the one form planned by the server, Make it
/// fit's fixes, a run and its Cancel, the made-up sample, the board's cards and a result's actions (Show the math,
/// Open as grid, Copy code, Run again).
/// </summary>
public sealed class AnalyzeClient
{
    private readonly ApiClient _api;

    public AnalyzeClient(ApiClient api)
    {
        _api = api;
    }

    public Task<AnalyzeToolbar> ToolbarAsync(string? front) =>
        _api.GetAsync<AnalyzeToolbar>(front is null ? "/analyze" : $"/analyze?front={ApiClient.Part(front)}");

    /// <summary>The form as the server plans it for an analysis on a table, with the user's picks and options so far.</summary>
    public Task<AnalyzePlan> PlanAsync(string analysis, string? table, JsonElement? columns, JsonElement? options) =>
        _api.PostAsync<AnalyzePlan>("/analyze/plan", new { analysis, table, columns, options });

    /// <summary>Make it fit: the fixes' steps added to the table (undone in its steps strip), then the form again.</summary>
    public Task<AnalyzePlan> FixAsync(string analysis, string table, IReadOnlyList<string> fixes, JsonElement? columns) =>
        _api.PostAsync<AnalyzePlan>("/analyze/fix", new { analysis, table, fixes, columns });

    /// <summary>Run it; its cards land at the top of the board. A run is stopped by its token (Cancel).</summary>
    public Task<AnalyzeRun> RunAsync(string analysis, string? table, JsonElement? columns, JsonElement? options, string token, CancellationToken cancel) =>
        _api.PostAsync<AnalyzeRun>("/analyze/run", new { analysis, table, columns, options, token }, cancel);

    /// <summary>Run it on the contract's made-up sample (opened as a table of its own).</summary>
    public Task<AnalyzeRun> RunSampleAsync(string analysis, string token, CancellationToken cancel) =>
        _api.PostAsync<AnalyzeRun>("/analyze/run", new { analysis, sample = true, token }, cancel);

    public Task CancelAsync(string token) => _api.PostAsync("/analyze/cancel", new { token });

    public Task<BoardCards> CardsAsync() => _api.GetAsync<BoardCards>("/cards");

    public Task DeleteCardAsync(string card) => _api.DeleteAsync<RemovedCard>($"/cards/{ApiClient.Part(card)}");

    public Task<RunMath> MathAsync(string run) => _api.GetAsync<RunMath>($"/analyze/runs/{ApiClient.Part(run)}/math");

    public Task<RunCode> CodeAsync(string run) => _api.GetAsync<RunCode>($"/analyze/runs/{ApiClient.Part(run)}/code");

    public Task<RunInputs> InputsAsync(string run) => _api.GetAsync<RunInputs>($"/analyze/runs/{ApiClient.Part(run)}");

    /// <summary>Open as grid: the result's rows in a table of their own.</summary>
    public Task<MadeTable> OpenGridAsync(string run) => _api.PostAsync<MadeTable>($"/analyze/runs/{ApiClient.Part(run)}/grid");
}
