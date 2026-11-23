using System.Text.Json;

namespace SwissArmyBench.Web.Pages.Grids.Steps;

public partial class CategorizeForm
{
    private readonly List<CategoryRule> _rules = [];
    private string _column = string.Empty;
    private string _as = "category";
    private string _unmatched = "Other";

    protected override void OnInitialized()
    {
        _column = Text("column", Columns.FirstOrDefault(c => ColumnTypes.IsText(c.Type) || ColumnTypes.IsNumber(c.Type))?.Name ?? string.Empty);
        _as = Text("as", _as);
        _unmatched = Text("unmatched", _unmatched);
        var given = Items("rules")
            .Where(r => r.ValueKind == JsonValueKind.Object)
            .Select(r => new CategoryRule
            {
                Type = Field(r, "type", "wildcard"),
                Value = ValuesOf(r) ?? Field(r, "value", Field(r, "low", string.Empty)),
                High = Field(r, "high", string.Empty),
                Label = Field(r, "label", string.Empty),
            });
        _rules.AddRange(given);
        if (_rules.Count == 0)
        {
            _rules.Add(new CategoryRule());
        }
    }

    public override Dictionary<string, object?> Read()
    {
        var rules = _rules.Select(rule =>
        {
            var one = new Dictionary<string, object?> { ["type"] = rule.Type, ["label"] = rule.Label };
            switch (rule.Type)
            {
                case "range":
                    one["low"] = Number(rule.Value, "From");
                    one["high"] = Number(rule.High, "Up to");
                    break;
                case "in":
                    one["values"] = rule.Value.Split(['\n', ','], StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries).ToList();
                    break;
                default:
                    one["value"] = rule.Value;
                    break;
            }
            return one;
        }).ToList();
        return new() { ["column"] = _column, ["as"] = _as.Trim(), ["unmatched"] = _unmatched, ["rules"] = rules };
    }

    /// <summary>An "is one of" rule's values, written back as the box shows them ("a, b, c").</summary>
    private static string? ValuesOf(JsonElement rule) =>
        rule.TryGetProperty("values", out var list) && list.ValueKind == JsonValueKind.Array
            ? string.Join(", ", list.EnumerateArray().Select(v => v.ValueKind == JsonValueKind.String ? v.GetString() : v.GetRawText()))
            : null;

    private static string Field(JsonElement rule, string name, string fallback) =>
        rule.TryGetProperty(name, out var value) && value.ValueKind is not JsonValueKind.Null
            ? (value.ValueKind == JsonValueKind.String ? value.GetString()! : value.GetRawText())
            : fallback;
}
