using System.Text.Json;

using SwissArmyBench.Web.Api.Grids;

namespace SwissArmyBench.Web.Api.Analyze;

/// <summary>
/// The Analyze page (routes_analyze.py, routes_cards.py): the toolbar, the one form planned by the server, Make it
/// fit's fixes, a run and its Cancel, the made-up sample, the board's cards and a result's actions (Show the math,
/// Open as table, Copy code, Run again).
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

    /// <summary>Run it on the contract's made-up sample (opened on the Tables page of its own).</summary>
    public Task<AnalyzeRun> RunSampleAsync(string analysis, string token, CancellationToken cancel) =>
        _api.PostAsync<AnalyzeRun>("/analyze/run", new { analysis, sample = true, token }, cancel);

    public Task CancelAsync(string token) => _api.PostAsync("/analyze/cancel", new { token });

    public Task<BoardCards> CardsAsync() => _api.GetAsync<BoardCards>("/cards");

    public Task DeleteCardAsync(string card) => _api.DeleteAsync<RemovedCard>($"/cards/{ApiClient.Part(card)}");

    public Task<RunMath> MathAsync(string run) => _api.GetAsync<RunMath>($"/analyze/runs/{ApiClient.Part(run)}/math");

    public Task<RunCode> CodeAsync(string run) => _api.GetAsync<RunCode>($"/analyze/runs/{ApiClient.Part(run)}/code");

    public Task<RunInputs> InputsAsync(string run) => _api.GetAsync<RunInputs>($"/analyze/runs/{ApiClient.Part(run)}");

    /// <summary>Open as table: the result's rows in a table of their own.</summary>
    public Task<MadeTable> OpenGridAsync(string run) => _api.PostAsync<MadeTable>($"/analyze/runs/{ApiClient.Part(run)}/grid");

    /// <summary>Check this table: every analysis ranked on it.</summary>
    public Task<CheckAnswer> CheckAsync(string? table) => _api.PostAsync<CheckAnswer>("/analyze/check", new { table });

    /// <summary>What can I do with a column? Each column with the analyses that fit it.</summary>
    public Task<ColumnsAnswer> ColumnsAsync(string? table) => _api.PostAsync<ColumnsAnswer>("/analyze/column", new { table });

    /// <summary>One click: run with the rest defaulted (the analysis's fixes applied first when asked).</summary>
    public Task<AnalyzeRun> RunOneAsync(string analysis, string table, JsonElement? columns, bool applyFixes) =>
        _api.PostAsync<AnalyzeRun>("/analyze/run", new { analysis, table, columns, apply_fixes = applyFixes });

    /// <summary>Add chart: a chart card drawn on a table (its spec: mark, x, y, series).</summary>
    public Task AddChartAsync(string grid, string title, JsonElement spec) =>
        _api.PostAsync($"/grids/{ApiClient.Part(grid)}/cards", new { kind = "chart", title, spec });

    /// <summary>The cross-filter: a chart's bar, point or cell filters its own table (a heatmap cell by its row too).</summary>
    public Task SelectAsync(string card, JsonElement value, JsonElement? y) =>
        y is { } row
            ? _api.PostAsync($"/cards/{ApiClient.Part(card)}/select", new { value, y = row })
            : _api.PostAsync($"/cards/{ApiClient.Part(card)}/select", new { value });

    /// <summary>Copy as Python (Altair): the chart card's code.</summary>
    public Task<CardCode> ChartCodeAsync(string card) => _api.GetAsync<CardCode>($"/cards/{ApiClient.Part(card)}/code");
}
