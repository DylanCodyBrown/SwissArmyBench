using System.Text.Json;

using Microsoft.AspNetCore.Components;
using Microsoft.JSInterop;

using SwissArmyBench.Web.Api;
using SwissArmyBench.Web.Api.Apis;
using SwissArmyBench.Web.Api.Structures;
using SwissArmyBench.Web.State;

namespace SwissArmyBench.Web.Pages.Apis;

public partial class ApiExplorerView
{
    private static readonly JsonSerializerOptions _indented = new() { WriteIndented = true };

    private readonly Dictionary<string, string> _inputs = [];
    private string? _body;
    private bool _sending;
    private ApiCallAnswer? _answer;
    private StructureDocument? _structure;
    private Exception? _error;
    private string? _shownFor;
    private bool _asTable;
    private string _records = "$";
    private string _query = string.Empty;
    private bool _queryEdited;
    private bool _saving;
    private string? _sqlName;
    private bool _writing;
    private bool _discovering;
    private string? _allowedSince;
    private IReadOnlyDictionary<string, ActionLearned> _learned = new Dictionary<string, ActionLearned>();
    private ApiExplorer? _learnedFor;

    [Inject]
    private ApisClient Apis { get; set; } = default!;

    [Inject]
    private StructuresClient Structures { get; set; } = default!;

    [Inject]
    private Notes Notes { get; set; } = default!;

    [Inject]
    private IJSRuntime Js { get; set; } = default!;

    [Parameter, EditorRequired]
    public ApiExplorer Explorer { get; set; } = default!;

    /// <summary>The operation shown (its id); none: the first.</summary>
    [Parameter]
    public string? Operation { get; set; }

    private ApiOperation? Picked => Explorer.Operations.FirstOrDefault(o => o.Id == Operation) ?? Explorer.Operations.FirstOrDefault();

    protected override async Task OnParametersSetAsync()
    {
        if (!ReferenceEquals(_learnedFor, Explorer))
        {
            _learnedFor = Explorer;
            await LearnedAsync();
        }
        if (Picked?.Id == _shownFor)
        {
            return;
        }
        _shownFor = Picked?.Id;
        _inputs.Clear();
        _body = null;
        _answer = null;
        _structure = null;
        _asTable = Picked?.AsTable ?? false;
        _records = TableText(Picked, "records") is { Length: > 0 } records ? records : "$";
        _query = TableText(Picked, "conversion") ?? string.Empty;
        _queryEdited = false;
        _sqlName = null;
        _writing = false;
    }

    private static bool Writes(ApiOperation op) => op.Method is "POST" or "PUT" or "PATCH" or "DELETE";

    private IReadOnlyDictionary<string, string> TypedInputs() => _inputs.Where(i => i.Value.Length > 0).ToDictionary(i => i.Key, i => i.Value);

    /// <summary>What was learned of each action (the operations' kind and drift marks) and since when Discover is
    /// allowed.</summary>
    private async Task LearnedAsync()
    {
        try
        {
            var got = (await Apis.ActionsAsync(Explorer.Name)).Apis.FirstOrDefault();
            _allowedSince = got?.AllowedSince;
            _learned = (got?.Actions ?? []).ToDictionary(a => a.Name);
        }
        catch (ApiException)
        {
            _learned = new Dictionary<string, ActionLearned>(); // nothing learned to show
        }
    }

    /// <summary>Discover: the read-only probe on the user's Allow (asked once per API, then remembered).</summary>
    private async Task DiscoverAsync()
    {
        _discovering = true;
        try
        {
            var got = await Apis.DiscoverAsync(Explorer.Name);
            _ = Notes.SayAsync($"{Explorer.Name}: {got.Calls} call{(got.Calls == 1 ? string.Empty : "s")} made, nothing that writes.");
            await LearnedAsync();
            _error = null;
        }
        catch (ApiException error)
        {
            _error = error;
        }
        _discovering = false;
    }

    private async Task ForgetAsync()
    {
        try
        {
            await Apis.ForgetDiscoverAsync(Explorer.Name);
            _allowedSince = null;
        }
        catch (ApiException error)
        {
            _error = error;
        }
    }

    /// <summary>A saved table's DuckDB query: Save the query as typed, or Make it again from the rows path.</summary>
    private async Task SaveQueryAsync(bool made)
    {
        if (Picked is not { } op)
        {
            return;
        }
        try
        {
            var call = made
                ? new Dictionary<string, object?> { ["as_table"] = true, ["records"] = _records.Trim().Length > 0 ? _records.Trim() : "$" }
                : new Dictionary<string, object?> { ["as_table"] = true, ["conversion"] = _query };
            var done = await Apis.SaveCallAsync(Explorer.Name, op.Id, call);
            _query = done.WebCall?.Conversion ?? _query;
            _queryEdited = false;
            _ = Notes.SayAsync(made ? "The query is made again from the settings." : "Saved the query.");
            _error = null;
        }
        catch (ApiException error)
        {
            _error = error;
        }
    }

    private static string? TableText(ApiOperation? op, string key) =>
        op?.Table is { ValueKind: JsonValueKind.Object } table && table.TryGetProperty(key, out var value) && value.ValueKind == JsonValueKind.String
            ? value.GetString()
            : null;

    private void QueryTyped(ChangeEventArgs e)
    {
        _query = e.Value?.ToString() ?? string.Empty;
        _queryEdited = true;
    }

    /// <summary>Save as web call: the inputs and body as typed; Return as table on, where its rows are and the DuckDB
    /// query (sent only when edited: else made from the rows path).</summary>
    private async Task SaveAsync()
    {
        if (Picked is not { } op)
        {
            return;
        }
        _saving = true;
        try
        {
            var call = new Dictionary<string, object?>
            {
                ["inputs"] = _inputs.Where(i => i.Value.Length > 0).ToDictionary(i => i.Key, i => i.Value),
                ["as_table"] = _asTable,
            };
            if (op.Body is { } given)
            {
                call["body"] = JsonDocument.Parse(_body ?? BodyExample(given)).RootElement.Clone();
            }
            if (_asTable)
            {
                call["records"] = _records.Trim().Length > 0 ? _records.Trim() : "$";
                if (_queryEdited && _query.Trim().Length > 0)
                {
                    call["conversion"] = _query;
                }
            }
            var done = await Apis.SaveCallAsync(Explorer.Name, op.Id, call);
            _sqlName = done.SqlName;
            _ = Notes.SayAsync(done.SqlName is { } table ? $"Saved {done.Blade}: {table} is a table." : $"Saved {done.Blade}.");
            _error = null;
        }
        catch (ApiException error)
        {
            _error = error;
        }
        catch (JsonException)
        {
            _error = new ApiException(0, new Refusal("The body is not JSON: check its brackets and quotes."), string.Empty);
        }
        _saving = false;
    }

    private async Task CopySqlNameAsync(string name)
    {
        await Js.InvokeAsync<bool>("sab.copy", name);
        _ = Notes.SayAsync($"Copied {name}");
    }

    private string AddressOf(ApiOperation operation) => $"apis?name={Uri.EscapeDataString(Explorer.Name)}&operation={Uri.EscapeDataString(operation.Id)}";

    /// <summary>The body to start from: the operation's made-up example.</summary>
    private static string BodyExample(JsonElement body) =>
        body.TryGetProperty("example", out var example) ? Pretty(example) : "{}";

    private static string Pretty(JsonElement value) => JsonSerializer.Serialize(value, _indented);

    private async Task SendAsync()
    {
        if (Picked is not { } op)
        {
            return;
        }
        _sending = true;
        try
        {
            var body = op.Body is { } given ? JsonDocument.Parse(_body ?? BodyExample(given)).RootElement.Clone() : (JsonElement?)null;
            var inputs = _inputs.Where(i => i.Value.Length > 0).ToDictionary(i => i.Key, i => i.Value);
            _answer = await Apis.CallAsync(Explorer.Name, op.Id, inputs, body);
            _structure = _answer.Structure is { } id ? await Structures.GetAsync(id) : null;
            _error = null;
        }
        catch (ApiException error)
        {
            _error = error;
        }
        catch (JsonException)
        {
            _error = new ApiException(0, new Refusal("The body is not JSON: check its brackets and quotes."), string.Empty);
        }
        _sending = false;
    }
}
