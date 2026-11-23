using System.Text.Json;

using Microsoft.AspNetCore.Components;

using SwissArmyBench.Web.Api.Canvas;
using SwissArmyBench.Web.Api.Widgets;

namespace SwissArmyBench.Web.Pages.Canvas;

public partial class InputField
{
    private string? _typing;
    private string? _said;
    private ElementReference _typedBox;

    [Parameter, EditorRequired]
    public WidgetPort Port { get; set; } = new();

    /// <summary>The instance's id.</summary>
    [Parameter, EditorRequired]
    public string Id { get; set; } = string.Empty;

    [Parameter]
    public string Page { get; set; } = string.Empty;

    /// <summary>Its wire as the instance has it (null: not wired).</summary>
    [Parameter]
    public JsonElement? Given { get; set; }

    [Parameter, EditorRequired]
    public CanvasWiring Wiring { get; set; } = default!;

    [Parameter]
    public WidgetContext? Context { get; set; }

    [Parameter]
    public IReadOnlyDictionary<string, string> PageNames { get; set; } = new Dictionary<string, string>();

    [Parameter]
    public bool Editable { get; set; }

    /// <summary>The wire sent (null: not wired); the answer is what is wrong (empty: kept).</summary>
    [Parameter]
    public Func<object?, Task<string>> OnWire { get; set; } = _ => Task.FromResult(string.Empty);

    private string Current => WiringRules.KeyOf(Given);

    private bool IsTableList => Port.Type.StartsWith("list[Table", StringComparison.Ordinal);

    private BrokenWire? Broken => Wiring.Broken.FirstOrDefault(b => b.Instance == Id && b.Port == Port.Name);

    private string Line => _said ?? (Broken is { } broken ? $"{broken.Reason} It takes its starting value until it is wired again." : string.Empty);

    private WireLine? Auto => Given is null ? Wiring.Wires.FirstOrDefault(w => w.Auto && w.To == $"{Id}.{Port.Name}") : null;

    private string NotWiredWords => Auto is { } auto
        ? $"Automatic: {WiringRules.OutWords(auto.From, Wiring, Page, PageNames)}"
        : $"Not wired ({(Port.Default.ValueKind is JsonValueKind.Null or JsonValueKind.Undefined ? "none" : Port.Default.GetRawText())})";

    private IReadOnlyList<JsonElement> Items =>
        Given is { ValueKind: JsonValueKind.Object } given && given.TryGetProperty("tables", out var tables) && tables.ValueKind == JsonValueKind.Array
            ? tables.EnumerateArray().ToList()
            : [];

    private IReadOnlyList<PickGroup> TableChoices =>
        [.. SourceOptions.Tables(Context), .. SourceOptions.Outs(Port, Id, Page, Wiring, tablesOnly: true, PageNames)];

    private IReadOnlyList<PickGroup> SourceChoices =>
    [
        .. Port.Type == "Table" ? SourceOptions.Tables(Context) : [],
        .. SourceOptions.Outs(Port, Id, Page, Wiring, tablesOnly: false, PageNames),
        .. SourceOptions.Endpoints(Port, Context),
        .. SourceOptions.Variables(Port, Context),
    ];

    private string TypedValue => _typing switch
    {
        "value" when Given is { } g && g.TryGetProperty("value", out var v) => Port.Type == "str" ? Widgets.PropertyValues.Text(v) : v.GetRawText(),
        "page" when Given is { } g && g.TryGetProperty("page", out var p) => p.GetString() ?? string.Empty,
        _ => string.Empty,
    };

    protected override void OnParametersSet()
    {
        _said = null;
        _typing = Current is "value" or "page" ? Current : _typing is not null && Current.Length == 0 ? _typing : null;
    }

    private bool Listed(string value) => SourceChoices.Any(g => g.Options.Any(o => o.Value == value));

    private async Task SendAsync(object? wire) => _said = await OnWire(wire);

    private async Task PickedAsync(string? picked)
    {
        if (picked is "value" or "page")
        {
            _typing = picked;
            StateHasChanged();
            await Task.Yield();
            await _typedBox.FocusAsync();
            return;
        }
        _typing = null;
        await SendAsync(WiringRules.WireOf(picked ?? string.Empty));
    }

    private Task TypedAsync(string? raw)
    {
        raw ??= string.Empty;
        if (_typing == "page")
        {
            return SendAsync(new Dictionary<string, object?> { ["page"] = raw.Trim() });
        }
        if (Port.Type == "str")
        {
            return SendAsync(new Dictionary<string, object?> { ["value"] = raw });
        }
        if (Widgets.PropertyValues.Parsed(raw) is { } parsed)
        {
            return SendAsync(new Dictionary<string, object?> { ["value"] = parsed });
        }
        var example = Port.Type == "bool" ? "true" : Port.Type.StartsWith("list", StringComparison.Ordinal) ? "[\"a\"]" : "3";
        _said = $"{Port.Name} takes {Port.Words}: as JSON, such as {example}.";
        return Task.CompletedTask;
    }

    private Task PutAsync(IEnumerable<object> items)
    {
        var next = items.ToList();
        return SendAsync(next.Count > 0 ? new Dictionary<string, object?> { ["tables"] = next } : null);
    }

    private Task PutItemAsync(int at, string? picked) =>
        PutAsync(Items.Select((item, i) => i == at && WiringRules.WireOf(picked ?? string.Empty) is { } made ? (object)made : item));

    private Task MoveAsync(int at, int by)
    {
        var next = Items.Cast<object>().ToList();
        var one = next[at];
        next.RemoveAt(at);
        next.Insert(Math.Clamp(at + by, 0, next.Count), one);
        return PutAsync(next);
    }

    private Task RemoveAsync(int at) => PutAsync(Items.Where((_, i) => i != at).Cast<object>());

    private Task AddAsync(string? picked) =>
        WiringRules.WireOf(picked ?? string.Empty) is { } made ? PutAsync(Items.Cast<object>().Append(made)) : Task.CompletedTask;
}
