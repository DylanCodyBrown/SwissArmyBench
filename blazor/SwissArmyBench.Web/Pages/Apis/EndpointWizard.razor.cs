using System.Text.Json;

using Microsoft.AspNetCore.Components;

using SwissArmyBench.Web.Api;
using SwissArmyBench.Web.Api.LocalApi;
using SwissArmyBench.Web.State;

namespace SwissArmyBench.Web.Pages.Apis;

/// <summary>New endpoint, the one wizard (the classic endpointWizard.ts). It has no rule of its own: the tables, the
/// ranking, the steps with their columns and defaults, the code and what is missing all come from POST
/// /local-api/plan as the table, the pattern and the fields change; Add to API.py is POST /local-api/scaffold.</summary>
public sealed partial class EndpointWizard : IDisposable
{
    private const int TypingPauseMilliseconds = 250;

    private static readonly (string Value, string Words)[] _totals =
    [
        ("count", "Count"), ("sum", "Sum"), ("avg", "Average"), ("min", "Smallest"), ("max", "Largest"), ("count_distinct", "Count of different values"),
    ];

    private IReadOnlyList<WizardTable>? _tables;
    private string _table = string.Empty;
    private string _pattern = string.Empty;
    private string _other = string.Empty;
    private Dictionary<string, object?> _fields = [];
    private IReadOnlyList<WizardRanked> _ranked = [];
    private WizardPatternPlan? _shown;
    private IReadOnlyList<string> _others = [];
    private WizardPlan? _last;
    private Exception? _error;
    private bool _adding;
    private int _asked;
    private CancellationTokenSource? _typing;

    [Inject]
    private LocalApiClient LocalApi { get; set; } = default!;

    [Inject]
    private Notes Notes { get; set; } = default!;

    [Inject]
    private NavigationManager Nav { get; set; } = default!;

    /// <summary>The sandbox table to start on (the sandbox panel's row); none: the first.</summary>
    [Parameter]
    public string? Table { get; set; }

    /// <summary>The pattern to start on; none: the first that fits.</summary>
    [Parameter]
    public string? Pattern { get; set; }

    [Parameter]
    public EventCallback OnClose { get; set; }

    protected override async Task OnInitializedAsync()
    {
        try
        {
            _tables = (await LocalApi.PlanAsync(new Dictionary<string, object?>())).Tables;
        }
        catch (ApiException error)
        {
            _error = error;
            return;
        }
        if (_tables.Count == 0)
        {
            return;
        }
        _table = _tables.FirstOrDefault(t => t.Name == Table)?.Name ?? _tables[0].Name;
        _pattern = Pattern ?? string.Empty;
        await ReadAsync(true);
    }

    private static string TableWords(WizardTable t) => t.Rows is { } rows ? $"{t.Name} ({rows:N0} rows)" : t.Name;

    /// <summary>The server's answer drawn: the ranking and the steps when the table or the pattern changed, the
    /// code and what is missing always.</summary>
    private async Task ReadAsync(bool redraw)
    {
        var mine = ++_asked;
        WizardPlan plan;
        try
        {
            plan = await LocalApi.PlanAsync(Asked(redraw ? [] : _fields));
        }
        catch (ApiException error) when (mine == _asked)
        {
            _error = error;
            return;
        }
        if (mine != _asked)
        {
            return;
        }
        _error = null;
        if (_pattern.Length == 0)
        {
            _pattern = (plan.Ranked ?? []).FirstOrDefault(r => r.Fits)?.Pattern ?? "table";
            await ReadAsync(true);
            return;
        }
        if (redraw)
        {
            _fields = (plan.Plan?.Fields ?? new Dictionary<string, JsonElement>()).ToDictionary(f => f.Key, f => FieldOf(f.Value));
            _other = plan.Plan?.Steps.FirstOrDefault(s => s.Kind == "table")?.Value is { ValueKind: JsonValueKind.String } other ? other.GetString() ?? string.Empty : string.Empty;
            _ranked = plan.Ranked ?? [];
            _shown = plan.Plan;
            _others = plan.Others ?? [];
        }
        _last = plan;
    }

    /// <summary>What the server is asked: the table, the pattern and the other table when there is one, the fields.</summary>
    private Dictionary<string, object?> Asked(Dictionary<string, object?> fields)
    {
        var asked = new Dictionary<string, object?> { ["table"] = _table, ["fields"] = fields };
        if (_pattern.Length > 0)
        {
            asked["pattern"] = _pattern;
        }
        if (_other.Length > 0)
        {
            asked["other"] = _other;
        }
        return asked;
    }

    /// <summary>A field as the server gives it: a word, a list of words, rows of words, or nothing.</summary>
    private static object? FieldOf(JsonElement value) => value.ValueKind switch
    {
        JsonValueKind.String => value.GetString(),
        JsonValueKind.Array when value.EnumerateArray().All(v => v.ValueKind == JsonValueKind.Object) && value.GetArrayLength() > 0 =>
            value.EnumerateArray().Select(row => row.EnumerateObject().ToDictionary(p => p.Name, p => p.Value.ToString())).ToList(),
        JsonValueKind.Array => value.EnumerateArray().Select(v => v.ToString()).ToList(),
        JsonValueKind.Null or JsonValueKind.Undefined => null,
        _ => value.ToString(),
    };

    private string Text(string id) => _fields.GetValueOrDefault(id) as string ?? string.Empty;

    private List<string> Picked(string id) => _fields.GetValueOrDefault(id) as List<string> ?? [];

    private List<Dictionary<string, string>> Rows(string id) => _fields.GetValueOrDefault(id) as List<Dictionary<string, string>> ?? [];

    /// <summary>A step changed: the code asked again once the typing pauses (the other table: the steps again, at once).</summary>
    private void Changed(bool redraw = false)
    {
        _typing?.Cancel();
        _typing = new CancellationTokenSource();
        var token = _typing.Token;
        _ = InvokeAsync(async () =>
        {
            try
            {
                await Task.Delay(redraw ? 0 : TypingPauseMilliseconds, token);
            }
            catch (TaskCanceledException)
            {
                return;
            }
            await ReadAsync(redraw);
            StateHasChanged();
        });
    }

    private async Task TableChosenAsync(string? table)
    {
        _table = table ?? string.Empty;
        _pattern = string.Empty;
        _other = string.Empty;
        await ReadAsync(true);
    }

    private async Task PatternChosenAsync(string pattern)
    {
        _pattern = pattern;
        _other = string.Empty;
        await ReadAsync(true);
    }

    private void SetText(string id, ChangeEventArgs e)
    {
        _fields[id] = e.Value?.ToString() ?? string.Empty;
        Changed();
    }

    private void SetOther(ChangeEventArgs e)
    {
        _other = e.Value?.ToString() ?? string.Empty;
        Changed(true);
    }

    private void Tick(WizardStep step, string column, bool on)
    {
        var picked = Picked(step.Id).ToHashSet();
        _ = on ? picked.Add(column) : picked.Remove(column);
        _fields[step.Id] = step.Options.Where(picked.Contains).ToList();
        Changed();
    }

    private void SetRow(string id, int at, string key, ChangeEventArgs e)
    {
        var rows = Rows(id);
        rows[at][key] = e.Value?.ToString() ?? string.Empty;
        _fields[id] = rows;
        Changed();
    }

    private void AddRow(WizardStep step)
    {
        var rows = Rows(step.Id);
        rows.Add(step.Kind == "totals"
            ? new Dictionary<string, string> { ["fn"] = "count", ["column"] = string.Empty }
            : new Dictionary<string, string> { ["column"] = step.Options.FirstOrDefault() ?? string.Empty, ["value"] = string.Empty });
        _fields[step.Id] = rows;
        Changed();
    }

    private void RemoveRow(string id, int at)
    {
        var rows = Rows(id);
        rows.RemoveAt(at);
        _fields[id] = rows;
        Changed();
    }

    private string Said => _last?.Problem
        ?? $"{_last?.Added?.Count ?? 0} endpoint{((_last?.Added?.Count ?? 0) == 1 ? string.Empty : "s")} for API.py{(_last?.Words is { Length: > 0 } words ? $" ({words})" : string.Empty)}.";

    private string CodeText => _last is { Problem: null } plan
        ? $"{plan.Imports}{(string.IsNullOrEmpty(plan.Imports) ? string.Empty : "\n")}{plan.Code}"
        : string.Empty;

    /// <summary>Add to API.py: the endpoints appended, then the file opened on the new block.</summary>
    private async Task AddAsync()
    {
        _adding = true;
        try
        {
            var done = await LocalApi.ScaffoldAsync(Asked(_fields));
            var count = done.Added.Count;
            _ = Notes.SayAsync($"API.py has {count} new endpoint{(count == 1 ? string.Empty : "s")} for {_table}.{(done.Note is { Length: > 0 } note ? $" {note}" : string.Empty)}");
            await OnClose.InvokeAsync();
            if (done.File.Length > 0)
            {
                Nav.NavigateTo($"scripts?path={Uri.EscapeDataString(done.File)}&line={done.Line}");
            }
        }
        catch (ApiException error)
        {
            _error = error;
        }
        _adding = false;
    }

    public void Dispose()
    {
        _typing?.Cancel();
        _typing?.Dispose();
    }
}
