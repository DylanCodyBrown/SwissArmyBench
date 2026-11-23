using System.Globalization;
using System.Text.Json;

using Microsoft.AspNetCore.Components;

using SwissArmyBench.Web.Api.Widgets;

namespace SwissArmyBench.Web.Pages.Widgets;

public partial class PropertyField
{
    // A path value's placeholder: a value, a variable or a page value (the dollar and the brace kept apart).
    private static readonly string _pathPlaceholder = "a value, $" + "{NAME} or {{ page value }}";

    private readonly string _listId = $"wg-cols-{Guid.NewGuid():N}"[..20];

    private string? _said;

    private string ListId => _listId;

    [Parameter, EditorRequired]
    public WidgetProp Prop { get; set; } = new();

    /// <summary>Every property's value as the instance (or the code) has it: a column's table and a path's endpoint
    /// are other properties.</summary>
    [Parameter, EditorRequired]
    public IReadOnlyDictionary<string, JsonElement> Values { get; set; } = new Dictionary<string, JsonElement>();

    /// <summary>What the pickers offer; the tables' columns by name (an Out's "out:w1.rows" among them).</summary>
    [Parameter]
    public WidgetContext? Context { get; set; }

    [Parameter]
    public bool ReadOnly { get; set; }

    /// <summary>The value, checked and kept by the caller: its answer is the line under the box (empty: kept).</summary>
    [Parameter]
    public Func<object?, Task<string>>? OnValue { get; set; }

    /// <summary>The server's mark on this property (an instance's value that no longer fits).</summary>
    [Parameter]
    public string? Marked { get; set; }

    /// <summary>The instance sets its own value: Back to the default is offered.</summary>
    [Parameter]
    public bool Overridden { get; set; }

    [Parameter]
    public EventCallback OnReset { get; set; }

    private JsonElement? Value => Values.TryGetValue(Prop.Name, out var given) && given.ValueKind != JsonValueKind.Null ? given : Prop.Default;

    private string Text => PropertyValues.Text(Value);

    private string Line => _said ?? Marked ?? Prop.Problem ?? string.Empty;

    private string StepText => Prop.Step is { } step ? step.ToString(CultureInfo.InvariantCulture) : Prop.Type == "int" ? "1" : "any";

    private string ColourShown => System.Text.RegularExpressions.Regex.IsMatch(Text, "^#[0-9a-fA-F]{6}$") ? Text : "#000000";

    private IReadOnlyList<string> Endpoints => Context?.Endpoints ?? [];

    private IEnumerable<string> KnownEndpoints => Text.Length == 0 || Endpoints.Contains(Text) ? Endpoints : Endpoints.Prepend(Text);

    private string OfValue => Prop.Of is { } of && Values.TryGetValue(of, out var given) ? PropertyValues.Text(given) : string.Empty;

    protected override void OnParametersSet() => _said = null;

    private async Task SendAsync(object? next)
    {
        if (OnValue is null)
        {
            return;
        }
        try
        {
            _said = await OnValue(next);
        }
        catch (Exception error) when (error is SwissArmyBench.Web.Api.ApiException or InvalidOperationException)
        {
            _said = error is SwissArmyBench.Web.Api.ApiException api ? api.Refusal.Error : error.Message;
        }
    }

    private Task NumberAsync(string? text)
    {
        if (PropertyValues.Number(text ?? string.Empty, Prop.Type) is not { } number)
        {
            _said = $"{Prop.Name} is a number.";
            return Task.CompletedTask;
        }
        return SendAsync(number);
    }

    private void JsonTyped(string? text) =>
        _said = PropertyValues.Parsed(text ?? string.Empty) is null ? "Not JSON yet: [\"a\", \"b\"] or {\"name\": 1}." : string.Empty;

    private Task JsonAsync(string? text) =>
        PropertyValues.Parsed(text ?? string.Empty) is { } parsed ? SendAsync(parsed) : Task.CompletedTask;

    /// <summary>A path value typed: every box's value, the empty ones left out.</summary>
    private Task PathValueAsync(string name, string? typed)
    {
        var next = PropertyValues.Map(Value).ToDictionary(p => p.Key, p => p.Value);
        next[name] = (typed ?? string.Empty).Trim();
        return SendAsync(next.Where(p => p.Value.Length > 0).ToDictionary(p => p.Key, p => (object?)p.Value));
    }

    /// <summary>The columns of the table its `of` property names (the made-up sample's with none).</summary>
    private IReadOnlyList<string> Columns
    {
        get
        {
            var table = OfValue;
            if (table.Length == 0)
            {
                return PropertyValues.SampleColumns;
            }
            return Context?.Tables.GetValueOrDefault(table) ?? [];
        }
    }
}
