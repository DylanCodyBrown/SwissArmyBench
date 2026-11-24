using System.Text.Json;

using Microsoft.AspNetCore.Components;
using Microsoft.JSInterop;

using SwissArmyBench.Web.Api;
using SwissArmyBench.Web.Api.Grids;
using SwissArmyBench.Web.Pages.Grids.Cards;
using SwissArmyBench.Web.State;

namespace SwissArmyBench.Web.Pages.Grids;

public partial class PanelWindow
{
    public const string Steps = "steps";
    public const string Keys = "keys";
    public const string ConnectionSql = "connsql";

    private GridInfo? _info;
    private int? _previewUpto;
    private StepRequest? _editor;
    private Exception? _error;

    [Inject]
    private GridsClient Grids { get; set; } = default!;

    [Inject]
    private ApiClient Api { get; set; } = default!;

    [Inject]
    private LiveUpdates Live { get; set; } = default!;

    [Inject]
    private Notes Notes { get; set; } = default!;

    [Inject]
    private IJSRuntime Js { get; set; } = default!;

    [SupplyParameterFromQuery(Name = "panel")]
    public string? Panel { get; set; }

    [SupplyParameterFromQuery(Name = "grid")]
    public string? Grid { get; set; }

    /// <summary>The SQL window: the connection the queries run on.</summary>
    [SupplyParameterFromQuery(Name = "to")]
    public string? To { get; set; }

    /// <summary>The SQL window: the tables whose queries are looked over, in order.</summary>
    [SupplyParameterFromQuery(Name = "table")]
    public string[]? Tables { get; set; }

    /// <summary>The SQL window: the query to start from (Write a query…), for one table.</summary>
    [SupplyParameterFromQuery(Name = "sql")]
    public string? Sql { get; set; }

    /// <summary>The address of a pop-out window: the panel and its grid.</summary>
    public static string Address(string panel, string grid) => $"panel?panel={panel}&grid={ApiClient.Part(grid)}";

    /// <summary>The SQL window's address: the queries of <paramref name="tables"/>, run on <paramref name="to"/>.</summary>
    public static string SqlAddress(string to, IEnumerable<string> tables, string? sql) =>
        $"panel?panel={ConnectionSql}&to={ApiClient.Part(to)}{string.Concat(tables.Select(t => $"&table={ApiClient.Part(t)}"))}{(sql is null ? string.Empty : $"&sql={ApiClient.Part(sql)}")}";

    protected override async Task OnInitializedAsync()
    {
        Live.NoticeArrived += OnNotice;
        await LoadAsync();
    }

    private async Task LoadAsync()
    {
        if (Panel == ConnectionSql)
        {
            await Js.InvokeVoidAsync("sab.setTitle", $"{To} · SQL");
            return;
        }
        if (Grid is not { Length: > 0 } grid)
        {
            _error = new InvalidOperationException("This window names no table.");
            return;
        }
        try
        {
            _info = await Grids.InfoAsync(grid);
            await Js.InvokeVoidAsync("sab.setTitle", $"{(Panel == Keys ? "Key Finder" : "Transformations")} · {_info.Dataset}");
        }
        catch (ApiException error)
        {
            _error = error;
        }
    }

    // The grid page (or the agent) changed the grid: this window shows it as it is now.
    private void OnNotice(Notice notice)
    {
        if (Grid is not null && notice.Text("grid") == Grid && notice.Type is "grid_updated" or "grid_closed")
        {
            _ = InvokeAsync(async () =>
            {
                await LoadAsync();
                StateHasChanged();
            });
        }
    }

    private IReadOnlyList<GridColumn> Entering(int? index) =>
        index is { } at && _info?.StageColumns is { Count: > 0 } stages ? stages[Math.Min(at, stages.Count - 1)] : _info?.Columns ?? [];

    private Task ToggleAsync((int Index, bool Enabled) toggle) => ChangeAsync(() => Grids.ToggleStepAsync(Grid!, toggle.Index, toggle.Enabled));

    private async Task DeleteAsync(int index)
    {
        var words = _info?.Steps.ElementAtOrDefault(index)?.Description ?? string.Empty;
        await ChangeAsync(() => Grids.DeleteStepAsync(Grid!, index));
        _ = Notes.SayAsync($"Removed the step: {words}", "Undo", () => InvokeAsync(() => ChangeAsync(() => Grids.UndoAsync(Grid!))));
    }

    private Task ReorderAsync(IReadOnlyList<GridStep> steps) => ChangeAsync(() => Grids.SaveStepsAsync(Grid!, steps));

    private void Edit((string Kind, int? Index) edit)
    {
        var steps = _info?.Steps ?? [];
        _editor = edit.Index is { } index && index < steps.Count
            ? new StepRequest(steps[index].Kind, steps[index].Params, index)
            : new StepRequest(edit.Kind, JsonSerializer.SerializeToElement(new Dictionary<string, object>()), null);
    }

    /// <summary>A step's editor saved: a new step at the end, or the edited one in its place (its refusal shown in the
    /// editor).</summary>
    private async Task SaveStepAsync(Dictionary<string, object?> parameters)
    {
        if (_editor is not { } editor || _info is not { } info)
        {
            return;
        }
        if (editor.Index is { } index)
        {
            var edited = JsonSerializer.SerializeToElement(parameters, ApiClient.Json);
            _info = await Grids.SaveStepsAsync(info.Grid, info.Steps.Select((step, at) => at == index ? step with { Params = edited } : step).ToList());
        }
        else
        {
            _info = await Grids.AddStepAsync(info.Grid, editor.Kind, parameters);
        }
        StateHasChanged();
    }

    private async Task ChangeAsync(Func<Task<GridInfo>> change)
    {
        try
        {
            _info = await change();
            _error = null;
        }
        catch (ApiException error)
        {
            _error = error;
        }
        StateHasChanged();
    }

    /// <summary>The Key Finder's Send to Analyze: its note on the board.</summary>
    private async Task SendKeysAsync(KeyFinderResult result)
    {
        var targets = result.Targets.Select(t => t.GetProperty("dataset").GetString() ?? string.Empty).ToList();
        var cards = GridCards.KeyFinder(result, targets);
        try
        {
            foreach (var card in cards)
            {
                await Api.PostAsync($"/grids/{ApiClient.Part(Grid!)}/cards", card);
            }
            _ = Notes.SayAsync($"On the Analyze board: {(cards.Count == 1 ? "a note" : "a note and its chart")}.");
        }
        catch (ApiException error)
        {
            Notes.Error(error);
        }
    }

    private Task SwappedAsync(Swapped done) =>
        Notes.SayAsync($"{done.Table}: {done.To}");

    private async Task CloseWindowAsync() => await Js.InvokeVoidAsync("close");

    public void Dispose() => Live.NoticeArrived -= OnNotice;
}
