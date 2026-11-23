using System.Text.Json;

using Microsoft.AspNetCore.Components;
using Microsoft.AspNetCore.Components.Rendering;
using Microsoft.JSInterop;

using SwissArmyBench.Web.Components;
using SwissArmyBench.Web.State;

namespace SwissArmyBench.Web.Pages.Grids.Values;

public partial class ValueViewer
{
    // A table shows at most this many rows and columns of a long array.
    private const int MostRows = 500;
    private const int MostColumns = 40;

    private readonly List<(string Label, JsonElement Value)> _layers = [];
    private bool _raw;

    [Inject]
    private IJSRuntime Js { get; set; } = default!;

    [Inject]
    private Notes Notes { get; set; } = default!;

    /// <summary>Where the value is: "notes, row 12".</summary>
    [Parameter, EditorRequired]
    public string Title { get; set; } = string.Empty;

    [Parameter, EditorRequired]
    public JsonElement Value { get; set; }

    /// <summary>Send to Analyze: the layer shown and its trail ("notes, row 12 › items").</summary>
    [Parameter]
    public EventCallback<(JsonElement Value, string Trail)> OnSend { get; set; }

    [Parameter]
    public EventCallback OnClose { get; set; }

    private (string Label, JsonElement Value) Current => _layers[^1];

    private ValueShape Shape => ValueRules.Detect(Current.Value);

    private bool HasTabs => Shape is ValueShape.Object or ValueShape.Array or ValueShape.Table or ValueShape.Markdown;

    protected override void OnInitialized() => _layers.Add((Title, ValueRules.Parsed(Value)));

    private void Show(int depth)
    {
        _layers.RemoveRange(depth + 1, _layers.Count - depth - 1);
        _raw = false;
    }

    private void Drill(string label, JsonElement inner)
    {
        _layers.Add((label, ValueRules.Parsed(inner)));
        _raw = false;
    }

    private Task SendAsync() => OnSend.InvokeAsync((Current.Value, string.Join(" › ", _layers.Select(l => l.Label))));

    private async Task CopyAsync()
    {
        if (await Js.InvokeAsync<bool>("sab.copy", ValueRules.Copied(Current.Value)))
        {
            _ = Notes.SayAsync("Copied.");
        }
    }

    /// <summary>A layer drawn the way it reads best (the classic formatted()).</summary>
    private RenderFragment Formatted(JsonElement value) => builder =>
    {
        switch (ValueRules.Detect(value))
        {
            case ValueShape.Object:
                Table(builder, ["Key", "Value"], value.EnumerateObject().Select(p => (p.Name, (IReadOnlyList<(string, JsonElement)>)[(p.Name, p.Value)])), rowHeads: true);
                break;
            case ValueShape.Table:
                var items = value.EnumerateArray().Take(MostRows).ToList();
                var keys = items.SelectMany(i => i.EnumerateObject().Select(p => p.Name)).Distinct().Take(MostColumns).ToList();
                Table(builder, ["#", .. keys], items.Select((item, i) => (i.ToString(System.Globalization.CultureInfo.InvariantCulture),
                    (IReadOnlyList<(string, JsonElement)>)keys.Select(k => ($"[{i}].{k}", item.TryGetProperty(k, out var v) ? v : default)).ToList())), rowHeads: false);
                if (value.GetArrayLength() > MostRows)
                {
                    builder.OpenElement(0, "p");
                    builder.AddAttribute(1, "class", "hint");
                    builder.AddContent(2, $"First {MostRows} of {value.GetArrayLength():N0}.");
                    builder.CloseElement();
                }
                break;
            case ValueShape.Array:
                Table(builder, ["#", "Item"], value.EnumerateArray().Take(MostRows).Select((v, i) => (i.ToString(System.Globalization.CultureInfo.InvariantCulture), (IReadOnlyList<(string, JsonElement)>)[($"[{i}]", v)])), rowHeads: false);
                break;
            case ValueShape.Markdown:
                builder.OpenElement(0, "div");
                builder.AddAttribute(1, "class", "vv-markdown");
                builder.AddMarkupContent(2, MarkdownText.ToHtml(ValueRules.Text(value)));
                builder.CloseElement();
                break;
            case ValueShape.Blank:
                builder.OpenElement(0, "p");
                builder.AddAttribute(1, "class", "cell-blank");
                builder.AddContent(2, "(blank)");
                builder.CloseElement();
                break;
            default:
                builder.OpenElement(0, "pre");
                builder.AddAttribute(1, "class", "vv-text mono");
                builder.AddContent(2, ValueRules.Text(value));
                builder.CloseElement();
                break;
        }
    };

    /// <summary>A table: its heads, then each row's first cell (a key or a number) and its values.</summary>
    private void Table(RenderTreeBuilder builder, IReadOnlyList<string> heads, IEnumerable<(string First, IReadOnlyList<(string Label, JsonElement Value)> Cells)> rows, bool rowHeads)
    {
        builder.OpenElement(0, "table");
        builder.AddAttribute(1, "class", "vv-table");
        builder.OpenElement(2, "thead");
        builder.OpenElement(3, "tr");
        foreach (var head in heads)
        {
            builder.OpenElement(4, "th");
            builder.AddContent(5, head);
            builder.CloseElement();
        }
        builder.CloseElement();
        builder.CloseElement();
        builder.OpenElement(6, "tbody");
        foreach (var (first, cells) in rows)
        {
            builder.OpenElement(7, "tr");
            builder.OpenElement(8, rowHeads ? "th" : "td");
            builder.AddAttribute(9, "class", rowHeads ? null : "num");
            builder.AddContent(10, first);
            builder.CloseElement();
            foreach (var (label, cell) in cells)
            {
                builder.OpenElement(11, "td");
                Cell(builder, label, cell);
                builder.CloseElement();
            }
            builder.CloseElement();
        }
        builder.CloseElement();
        builder.CloseElement();
    }

    /// <summary>One value in a table: scalars inline, nested values (or JSON text) behind Open, long text cut.</summary>
    private void Cell(RenderTreeBuilder builder, string label, JsonElement value)
    {
        var inner = ValueRules.Parsed(value);
        if (inner.ValueKind is JsonValueKind.Null or JsonValueKind.Undefined)
        {
            builder.OpenElement(20, "span");
            builder.AddAttribute(21, "class", "cell-blank");
            builder.AddContent(22, "(blank)");
            builder.CloseElement();
            return;
        }
        if (inner.ValueKind is JsonValueKind.Object or JsonValueKind.Array)
        {
            var summary = ValueRules.Summary(inner);
            builder.OpenElement(23, "button");
            builder.AddAttribute(24, "type", "button");
            builder.AddAttribute(25, "class", "btn small vv-open");
            builder.AddAttribute(26, "title", $"Open {label}");
            builder.AddAttribute(27, "aria-label", $"Open {label}: {summary}");
            builder.AddAttribute(28, "onclick", EventCallback.Factory.Create(this, () => Drill(label, inner)));
            builder.AddContent(29, $"{summary} ›");
            builder.CloseElement();
            return;
        }
        var text = ValueRules.Text(inner);
        if (text.Length > ValueRules.LongText || text.Contains('\n'))
        {
            builder.OpenElement(30, "span");
            builder.AddAttribute(31, "class", "vv-long");
            builder.AddContent(32, $"{text[..Math.Min(text.Length, ValueRules.LongText)]}… ");
            builder.OpenElement(33, "button");
            builder.AddAttribute(34, "type", "button");
            builder.AddAttribute(35, "class", "link");
            builder.AddAttribute(36, "onclick", EventCallback.Factory.Create(this, () => Drill(label, inner)));
            builder.AddContent(37, "Open");
            builder.CloseElement();
            builder.CloseElement();
            return;
        }
        builder.OpenElement(38, "span");
        builder.AddAttribute(39, "class", inner.ValueKind == JsonValueKind.Number ? "num" : null);
        builder.AddContent(40, text);
        builder.CloseElement();
    }
}
