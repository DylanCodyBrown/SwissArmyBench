using System.Text.Json;

using Microsoft.AspNetCore.Components;

using SwissArmyBench.Web.Api;
using SwissArmyBench.Web.Api.Apis;

namespace SwissArmyBench.Web.Pages.Apis;

public sealed partial class ApiWriteRows
{
    private static readonly JsonSerializerOptions _indented = new() { WriteIndented = true };

    private IReadOnlyList<string>? _tables;
    private string _table = string.Empty;
    private IReadOnlyList<string> _columns = [];
    private readonly Dictionary<string, string> _from = [];
    private readonly Dictionary<string, string> _values = [];
    private bool _batch;
    private string? _working;
    private WriteRowsAnswer? _answer;
    private Exception? _error;

    [Parameter, EditorRequired]
    public string Api { get; set; } = string.Empty;

    [Parameter, EditorRequired]
    public ApiOperation Operation { get; set; } = default!;

    [Parameter]
    public EventCallback OnBack { get; set; }

    /// <summary>The fields a row can fill: each parameter (where.name), then each leaf of the body's schema
    /// (body.a.b; a key ending in * required).</summary>
    private IReadOnlyList<(string Field, bool Required)> Targets =>
    [
        .. Operation.Parameters.Select(p => ($"{p.In}.{p.Name}", p.Required)),
        .. Operation.Body is { } body && body.TryGetProperty("schema", out var schema) ? Leaves(schema, "body", true) : [],
    ];

    private static IEnumerable<(string Field, bool Required)> Leaves(JsonElement tree, string prefix, bool required)
    {
        if (tree.ValueKind != JsonValueKind.Object)
        {
            yield break;
        }
        foreach (var p in tree.EnumerateObject())
        {
            var name = p.Name.TrimEnd('*');
            var needed = required && p.Name.EndsWith('*');
            if (p.Value.ValueKind == JsonValueKind.Object && p.Value.EnumerateObject().Any())
            {
                foreach (var inner in Leaves(p.Value, $"{prefix}.{name}", needed))
                {
                    yield return inner;
                }
            }
            else if (p.Value.ValueKind != JsonValueKind.Array)
            {
                yield return ($"{prefix}.{name}", needed);
            }
        }
    }

    private string From(string field) => _from.GetValueOrDefault(field) ?? string.Empty;

    private static string Pretty(JsonElement value) => JsonSerializer.Serialize(value, _indented);

    protected override async Task OnInitializedAsync()
    {
        try
        {
            _tables = [.. (await Grids.ListAsync()).Select(g => g.Dataset).Distinct()];
            if (_tables.Count > 0)
            {
                _table = _tables[0];
                await ColumnsAsync();
            }
        }
        catch (ApiException error)
        {
            _error = error;
            _tables = [];
        }
    }

    private async Task TableChosenAsync(ChangeEventArgs e)
    {
        _table = e.Value?.ToString() ?? string.Empty;
        await ColumnsAsync();
    }

    /// <summary>The table's columns and the mapping matched by name (a dry run with no mapping).</summary>
    private async Task ColumnsAsync()
    {
        try
        {
            var dry = await Apis.WriteRowsAsync(Api, Operation.Id, new Dictionary<string, object?> { ["table"] = _table });
            _columns = dry.Columns ?? [];
            _from.Clear();
            _values.Clear();
            foreach (var (field, mapped) in dry.Mapping ?? new Dictionary<string, JsonElement>())
            {
                if (mapped.TryGetProperty("column", out var column))
                {
                    _from[field] = $"column:{column.GetString()}";
                }
                else if (mapped.TryGetProperty("value", out var value))
                {
                    _from[field] = "value";
                    _values[field] = value.GetRawText();
                }
            }
            _error = null;
        }
        catch (ApiException error)
        {
            _error = error;
        }
    }

    /// <summary>Each field's source: a column, or a value (JSON when it reads as JSON, else the text).</summary>
    private Dictionary<string, object?> Mapping()
    {
        var mapping = new Dictionary<string, object?>();
        foreach (var (field, from) in _from)
        {
            if (from.StartsWith("column:", StringComparison.Ordinal))
            {
                mapping[field] = new Dictionary<string, object?> { ["column"] = from[7..] };
            }
            else if (from == "value")
            {
                var typed = _values.GetValueOrDefault(field) ?? string.Empty;
                object? value;
                try
                {
                    value = JsonDocument.Parse(typed).RootElement.Clone();
                }
                catch (JsonException)
                {
                    value = typed;
                }
                mapping[field] = new Dictionary<string, object?> { ["value"] = value };
            }
        }
        return mapping;
    }

    private async Task RunAsync(bool dryRun)
    {
        _working = dryRun ? "dry" : "send";
        try
        {
            _answer = await Apis.WriteRowsAsync(Api, Operation.Id, new Dictionary<string, object?>
            {
                ["table"] = _table,
                ["mapping"] = Mapping(),
                ["batch"] = _batch,
                ["dry_run"] = dryRun,
            });
            _error = null;
            if (!dryRun && _answer.Structure is { } id)
            {
                Nav.NavigateTo($"structures?id={Uri.EscapeDataString(id)}");
            }
        }
        catch (ApiException error)
        {
            _error = error;
        }
        _working = null;
    }

    private async Task SaveAsync()
    {
        try
        {
            var saved = await Apis.SaveWriteAsync(Api, Operation.Id, new Dictionary<string, object?>
            {
                ["mapping"] = Mapping(),
                ["batch"] = _batch,
                ["table"] = _table,
            });
            _ = Notes.SayAsync($"Saved {saved.Blade}.");
        }
        catch (ApiException error)
        {
            _error = error;
        }
    }
}
