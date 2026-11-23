using System.Text.Json;

using Microsoft.AspNetCore.Components;

using SwissArmyBench.Web.Api;
using SwissArmyBench.Web.Api.Canvas;
using SwissArmyBench.Web.Api.Widgets;

namespace SwissArmyBench.Web.Pages.Canvas;

public partial class PropertiesPane
{
    [Inject]
    private WidgetsClient WidgetsApi { get; set; } = default!;

    [Parameter, EditorRequired]
    public CanvasView View { get; set; } = default!;

    [Parameter, EditorRequired]
    public IReadOnlyList<WidgetEntry> Widgets { get; set; } = [];

    [Parameter]
    public WidgetContext? Context { get; set; }

    [Parameter]
    public Func<string, Dictionary<string, object?>, Task<CanvasState?>> OnSend { get; set; } = default!;

    /// <summary>An In's source or an Event's actions sent; refused, it throws with the server's reason.</summary>
    [Parameter]
    public Func<WireChange, Task> OnWire { get; set; } = default!;

    [Parameter]
    public EventCallback<string?> OnEditWidget { get; set; }

    private IReadOnlyList<CanvasNode> Nodes => View.Selected.Select(View.Find).OfType<NodePlace>().Select(p => p.Node).ToList();

    private CanvasNode First => Nodes[0];

    private bool Same => Nodes.All(n => n.Kind == First.Kind && n.Widget == First.Widget);

    private WidgetEntry? Known => Widgets.FirstOrDefault(w => w.Name == First.Widget);

    private IReadOnlyDictionary<string, string> Marks => View.State?.Marks.GetValueOrDefault(First.Id) ?? new Dictionary<string, string>();

    private CanvasWiring? Wiring => View.State?.Wiring;

    private IReadOnlyList<WidgetPort> TableIns => Wiring?.Ports.GetValueOrDefault(First.Id)?.Ins.Where(p => p.Type == "Table").ToList() ?? [];

    /// <summary>The instance's values over the widget's defaults; an In[Table]'s value is its wire's table, or the Out
    /// it reads ("out:w1.rows"), so a column property offers that table's columns.</summary>
    private IReadOnlyDictionary<string, JsonElement> Values
    {
        get
        {
            var tables = TableIns.Select(port => KeyValuePair.Create(
                port.Name,
                JsonSerializer.SerializeToElement(SourceTable(Wiring?.Sources.GetValueOrDefault(First.Id)?.GetValueOrDefault(port.Name)))));
            return (Known?.Properties ?? [])
                .Select(p => KeyValuePair.Create(p.Name, p.Default))
                .Concat(First.Values ?? new Dictionary<string, JsonElement>())
                .Concat(tables)
                .GroupBy(pair => pair.Key)
                .ToDictionary(g => g.Key, g => g.Last().Value);
        }
    }

    /// <summary>The pickers' context with each wired Out's columns (declared, else as Play last saw them).</summary>
    private WidgetContext? FieldContext
    {
        get
        {
            if (Context is null)
            {
                return null;
            }
            var outs = TableIns
                .Select(port => Wiring?.Sources.GetValueOrDefault(First.Id)?.GetValueOrDefault(port.Name))
                .Select(source => source is { ValueKind: JsonValueKind.Object } s && s.TryGetProperty("out", out var o) ? o.GetString() : null)
                .OfType<string>()
                .ToList();
            var tables = Context.Tables.ToDictionary(t => t.Key, t => t.Value);
            outs.ForEach(o => tables[$"out:{o}"] = Wiring?.Columns.GetValueOrDefault(o));
            return Context with { Tables = tables };
        }
    }

    private static string SourceTable(JsonElement? source)
    {
        if (source is not { ValueKind: JsonValueKind.Object } given)
        {
            return string.Empty;
        }
        if (given.TryGetProperty("out", out var o))
        {
            return $"out:{o.GetString()}";
        }
        return given.TryGetProperty("table", out var t) ? t.GetString() ?? string.Empty : "?";
    }

    private JsonElement? WireOf(string port) => First.Wires?.TryGetValue(port, out var wire) == true ? wire : null;

    /// <summary>A value checked by the server first (what is wrong and its fix said under the box), then set on
    /// every selected instance.</summary>
    private async Task<string> SetValueAsync(string property, object? value)
    {
        if (Known is not { } known)
        {
            return string.Empty;
        }
        var nodes = Nodes;
        var checkedValue = await WidgetsApi.CheckValueAsync(new Dictionary<string, object?>
        {
            ["name"] = known.Name,
            ["property"] = property,
            ["value"] = value,
            ["values"] = Values,
        });
        if (!checkedValue.Ok)
        {
            return $"{checkedValue.Said ?? string.Empty} {checkedValue.Fix ?? string.Empty}".Trim();
        }
        foreach (var node in nodes)
        {
            await OnSend("set_values", new() { ["id"] = node.Id, ["values"] = new Dictionary<string, object?> { [property] = value } });
        }
        return string.Empty;
    }

    private Task ResetAsync(string property) =>
        OnSend("set_values", new() { ["id"] = First.Id, ["values"] = new Dictionary<string, object?> { [property] = null } });

    private async Task<string> WireAsync(string port, object? wire)
    {
        try
        {
            await OnWire(new WireChange(First.Id, port, wire));
            return string.Empty;
        }
        catch (ApiException error)
        {
            return error.Refusal.Error;
        }
    }
}
