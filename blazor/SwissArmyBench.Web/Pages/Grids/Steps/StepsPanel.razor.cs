using System.Text.Json;

using Microsoft.AspNetCore.Components;
using Microsoft.AspNetCore.Components.Web;
using Microsoft.JSInterop;

using SwissArmyBench.Web.Api;
using SwissArmyBench.Web.Api.Grids;
using SwissArmyBench.Web.State;

namespace SwissArmyBench.Web.Pages.Grids.Steps;

public partial class StepsPanel
{
    private string _tab = "steps";
    private IReadOnlyList<long> _counts = [];
    private readonly Dictionary<int, string> _categorize = [];
    private GridCode? _code;
    private Exception? _error;
    private int? _dragFrom;
    private long _countedFor = -1;

    [Inject]
    private ApiClient Api { get; set; } = default!;

    [Inject]
    private GridsClient Grids { get; set; } = default!;

    [Inject]
    private IJSRuntime Js { get; set; } = default!;

    [Inject]
    private Notes Notes { get; set; } = default!;

    [Parameter, EditorRequired]
    public GridInfo Info { get; set; } = default!;

    /// <summary>The step whose data the grid shows (0: the source), or null for the full view.</summary>
    [Parameter]
    public int? PreviewUpto { get; set; }

    [Parameter]
    public EventCallback<int?> OnPreview { get; set; }

    [Parameter]
    public EventCallback<(int Index, bool Enabled)> OnToggle { get; set; }

    [Parameter]
    public EventCallback<int> OnDelete { get; set; }

    /// <summary>A step's editor: its kind and the step (null: a new one).</summary>
    [Parameter]
    public EventCallback<(string Kind, int? Index)> OnEdit { get; set; }

    /// <summary>The steps in their new order.</summary>
    [Parameter]
    public EventCallback<IReadOnlyList<GridStep>> OnReorder { get; set; }

    [Parameter]
    public EventCallback OnClose { get; set; }

    protected override async Task OnParametersSetAsync()
    {
        if (Info.Gen == _countedFor)
        {
            return;
        }
        _countedFor = Info.Gen;
        try
        {
            var answer = await Api.GetAsync<StepCounts>($"/grids/{ApiClient.Part(Info.Grid)}/step-counts?gen={Info.Gen}&client={ApiClient.ClientId}");
            _counts = answer.Counts;
        }
        catch (ApiException)
        {
            _counts = [];
        }
        _categorize.Clear();
        foreach (var index in Info.Steps.Select((s, i) => (s, i)).Where(x => x.s.Kind == "categorize" && x.s.Enabled).Select(x => x.i))
        {
            await CategorizeStatsAsync(index);
        }
    }

    private async Task CategorizeStatsAsync(int index)
    {
        try
        {
            var stats = await Api.GetAsync<CategorizeStats>($"/grids/{ApiClient.Part(Info.Grid)}/categorize-stats?step={index}");
            var words = $"{stats.Unmatched:N0} rows matched no rule";
            _categorize[index] = stats.Overlapping > 0 ? $"{words} · ⚠ {stats.Overlapping:N0} matched more than one (first wins)" : words;
        }
        catch (ApiException)
        {
            // Shown only when it can be computed.
        }
    }

    private static bool Flag(GridStep step, string name) =>
        step.Params.ValueKind == JsonValueKind.Object && step.Params.TryGetProperty(name, out var value) && value.ValueKind == JsonValueKind.True;

    private Task AddSqlAsync() => OnEdit.InvokeAsync(("sql", null));

    private Task PreviewAsync(int? upto) => OnPreview.InvokeAsync(upto);

    private Task PreviewKeyAsync(KeyboardEventArgs e, int? upto) => e.Key == "Enter" ? OnPreview.InvokeAsync(upto) : Task.CompletedTask;

    private async Task MoveAsync(int to)
    {
        if (_dragFrom is not { } from || from == to)
        {
            return;
        }
        _dragFrom = null;
        var steps = Info.Steps.ToList();
        var moved = steps[from];
        steps.RemoveAt(from);
        steps.Insert(to, moved);
        await OnReorder.InvokeAsync(steps);
    }

    private async Task ShowCodeAsync()
    {
        _tab = "code";
        _code = null;
        try
        {
            _code = await Grids.CodeAsync(Info.Grid);
        }
        catch (ApiException error)
        {
            _error = error;
        }
    }

    private Task CopySqlAsync() => CopyAsync((_code?.Sql ?? string.Empty).Trim() + "\n", "SQL query");

    private Task CopyPythonAsync() => CopyAsync(_code?.Code ?? string.Empty, "Python");

    private async Task CopyAsync(string text, string what)
    {
        var copied = await Js.InvokeAsync<bool>("sab.copy", text);
        _ = Notes.SayAsync(copied ? $"Copied the verified {what}." : "The browser blocked the clipboard.");
    }
}
