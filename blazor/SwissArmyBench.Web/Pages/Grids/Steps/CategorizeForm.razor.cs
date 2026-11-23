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
        foreach (var given in Items("rules").Where(r => r.ValueKind == JsonValueKind.Object))
        {
            var values = given.TryGetProperty("values", out var list) && list.ValueKind == JsonValueKind.Array
                ? string.Join(", ", list.EnumerateArray().Select(v => v.ValueKind == JsonValueKind.String ? v.GetString() : v.GetRawText()))
                : null;
            _rules.Add(new CategoryRule
            {
                Type = Field(given, "type", "wildcard"),
                Value = values ?? Field(given, "value", Field(given, "low", string.Empty)),
                High = Field(given, "high", string.Empty),
                Label = Field(given, "label", string.Empty),
            });
        }
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

    private static string Field(JsonElement rule, string name, string fallback) =>
        rule.TryGetProperty(name, out var value) && value.ValueKind is not JsonValueKind.Null
            ? (value.ValueKind == JsonValueKind.String ? value.GetString()! : value.GetRawText())
            : fallback;
}
