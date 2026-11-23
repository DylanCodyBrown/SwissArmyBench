using System.Text.Json;

using Microsoft.AspNetCore.Components;

using SwissArmyBench.Web.Api;
using SwissArmyBench.Web.Api.Analyze;

namespace SwissArmyBench.Web.Pages.Analyze;

public partial class AnalyzeForm
{
    private Exception? _error;
    private bool _running;
    private string? _token;
    private CancellationTokenSource? _cancel;
    private int _asked;
    private int _runs;

    [Inject]
    private AnalyzeClient AnalyzeApi { get; set; } = default!;

    /// <summary>The analysis the form is for (outliers, benford...).</summary>
    [Parameter, EditorRequired]
    public string Analysis { get; set; } = string.Empty;

    /// <summary>The grid it starts on (the toolbar's current table).</summary>
    [Parameter]
    public string? Table { get; set; }

    /// <summary>What a Run again starts from: the run's columns and options.</summary>
    [Parameter]
    public RunInputs? Again { get; set; }

    [Parameter]
    public IReadOnlyList<AnalyzeTable> Tables { get; set; } = [];

    /// <summary>A run finished: its cards are on the board.</summary>
    [Parameter]
    public EventCallback<AnalyzeRun> OnRan { get; set; }

    public AnalyzePlan? Plan { get; private set; }

    private List<PlanFix> Needed => Plan?.Fixes.Where(f => f.Level == "needed").ToList() ?? [];

    private List<PlanFix> Better => Plan?.Fixes.Where(f => f.Level == "better").ToList() ?? [];

    private string? _shownFor;

    protected override async Task OnParametersSetAsync()
    {
        var wanted = $"{Analysis}|{Again?.Run}";
        if (wanted == _shownFor)
        {
            return;
        }
        _shownFor = wanted;
        Plan = null;
        await PlanAsync(Again?.Table ?? Table, Again?.Columns, Again?.Options);
    }

    private Task ReplanAsync() => PlanAsync(Plan?.Grid ?? Table, Plan?.Columns, Plan?.Settings);

    /// <summary>The form planned again by the server (only the newest answer is drawn).</summary>
    private async Task PlanAsync(string? table, JsonElement? columns, JsonElement? options)
    {
        var mine = ++_asked;
        try
        {
            var plan = await AnalyzeApi.PlanAsync(Analysis, table, columns, options);
            if (mine == _asked)
            {
                Plan = plan;
                _error = null;
            }
        }
        catch (ApiException error)
        {
            _error = error;
        }
    }

    private Task TableChangedAsync(ChangeEventArgs e) => PlanAsync(e.Value?.ToString(), null, null);

    private Task PickAsync((string Key, JsonElement Value) pick) => PlanAsync(Plan?.Grid, With(Plan?.Columns, pick.Key, pick.Value), Plan?.Settings);

    private Task OptionAsync((string Key, JsonElement Value) option) => PlanAsync(Plan?.Grid, Plan?.Columns, With(Plan?.Settings, option.Key, option.Value));

    /// <summary>An object of the plan's (its picks, its settings) with one field set.</summary>
    private static JsonElement With(JsonElement? given, string key, JsonElement value)
    {
        var fields = given is { ValueKind: JsonValueKind.Object } known
            ? known.EnumerateObject().ToDictionary(p => p.Name, p => p.Value)
            : [];
        fields[key] = value;
        return JsonSerializer.SerializeToElement(fields);
    }

    private async Task ApplyAsync(PlanFix fix)
    {
        if (Plan is not { } plan)
        {
            return;
        }
        try
        {
            Plan = await AnalyzeApi.FixAsync(plan.Analysis, plan.Grid, [fix.Id], plan.Columns);
            _error = null;
        }
        catch (ApiException error)
        {
            _error = error;
        }
    }

    /// <summary>Run the form (or the contract's sample), gated with Cancel while it runs; its cards land on the
    /// board by themselves. A sample's run moves the form onto the sample's table.</summary>
    private async Task RunAsync(bool sample)
    {
        if (Plan is not { } plan)
        {
            return;
        }
        _running = true;
        _token = $"blazor-{ApiClient.ClientId}-{++_runs}";
        _cancel = new CancellationTokenSource();
        try
        {
            var ran = sample
                ? await AnalyzeApi.RunSampleAsync(plan.Analysis, _token, _cancel.Token)
                : await AnalyzeApi.RunAsync(plan.Analysis, plan.Grid, plan.Columns, plan.Settings, _token, _cancel.Token);
            _error = null;
            if (sample)
            {
                await PlanAsync(ran.Table, ran.Columns, ran.Options);
            }
            await OnRan.InvokeAsync(ran);
        }
        catch (ApiException error)
        {
            _error = error;
        }
        catch (OperationCanceledException)
        {
            // Cancelled: nothing of it lands.
        }
        _running = false;
    }

    private async Task CancelAsync()
    {
        if (_token is { } token)
        {
            await AnalyzeApi.CancelAsync(token);
        }
        _cancel?.Cancel();
    }
}
