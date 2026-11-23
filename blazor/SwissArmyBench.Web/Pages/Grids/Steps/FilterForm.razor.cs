using System.Text.Json;

using Microsoft.AspNetCore.Components;

using SwissArmyBench.Web.Api;
using SwissArmyBench.Web.Api.Grids;

namespace SwissArmyBench.Web.Pages.Grids.Steps;

public partial class FilterForm
{
    private static readonly Dictionary<string, (string Op, string Words)[]> _conditions = new()
    {
        ["text"] =
        [
            ("eq", "equals"), ("ne", "does not equal"), ("in", "is one of"), ("not_in", "is none of"),
            ("contains", "contains"), ("starts_with", "starts with"), ("ends_with", "ends with"),
            ("blank", "is blank"), ("not_blank", "is not blank"),
        ],
        ["number"] =
        [
            ("eq", "equals"), ("ne", "does not equal"), ("lt", "less than"), ("gt", "greater than"),
            ("between", "between"), ("in", "is one of"), ("not_in", "is none of"),
            ("blank", "is blank"), ("not_blank", "is not blank"),
        ],
        ["date"] = [("before", "before"), ("after", "after"), ("date_between", "between"), ("eq", "on"), ("blank", "is blank"), ("not_blank", "is not blank")],
        ["boolean"] = [("true", "is true"), ("false", "is false"), ("blank", "is blank"), ("not_blank", "is not blank")],
    };

    private static readonly HashSet<string> _noValue = ["blank", "not_blank", "true", "false", "in", "not_in"];

    private Dictionary<string, JsonElement> _picked = [];
    private string _column = string.Empty;
    private string _op = "eq";
    private string _value = string.Empty;
    private string _high = string.Empty;
    private string _search = string.Empty;
    private ValueList? _values;
    private int _asked;

    [Inject]
    private GridsClient Grids { get; set; } = default!;

    private string Family => ColumnTypes.Family(TypeOf(_column));

    private (string Op, string Words)[] Conditions => _conditions[Family];

    private bool IsRange => _op is "between" or "date_between";

    private bool IsList => _op is "in" or "not_in";

    private bool NeedsValue => !_noValue.Contains(_op);

    private string InputType => Family switch
    {
        "date" => "date",
        "number" => "number",
        _ => "text",
    };

    // Ticked values the answer does not hold stay listed while nothing is searched, so an edited step shows them.
    private IEnumerable<ValueCount> Shown
    {
        get
        {
            var listed = _values?.Values ?? [];
            var extra = _search.Length > 0 ? [] : _picked.Where(p => listed.All(v => v.Value.GetRawText() != p.Key)).Select(p => new ValueCount { Value = p.Value });
            return extra.Concat(listed);
        }
    }

    private string FootWords
    {
        get
        {
            var words = new List<string> { $"{_picked.Count:N0} selected" };
            if (_values?.More == true)
            {
                words.Add("more values: search to find one");
            }
            if (_values?.Blanks > 0)
            {
                words.Add($"{_values.Blanks:N0} blank (the condition \"is blank\")");
            }
            return string.Join(" · ", words);
        }
    }

    protected override async Task OnInitializedAsync()
    {
        _column = Text("column", Columns.FirstOrDefault()?.Name ?? string.Empty);
        if (Columns.All(c => c.Name != _column))
        {
            _column = Columns.FirstOrDefault()?.Name ?? string.Empty;
        }
        // A new filter on a text or number column starts on its values to tick (Excel's way); a date's on a range.
        _op = Text("op", StartOp());
        _value = Raw("value", Raw("low"));
        _high = Raw("high");
        _picked = Items("values")
            .DistinctBy(v => v.GetRawText())
            .ToDictionary(v => v.GetRawText(), v => v.Clone());
        await LoadValuesAsync();
    }

    public override Dictionary<string, object?> Read()
    {
        var number = Family == "number";
        var read = new Dictionary<string, object?> { ["column"] = _column, ["op"] = _op };
        if (IsRange)
        {
            read["low"] = number ? Number(_value, "From") : _value;
            read["high"] = number ? Number(_high, "To") : _high;
        }
        else if (IsList)
        {
            if (_picked.Count == 0)
            {
                throw new StepFormException("Tick at least one value.");
            }
            read["values"] = _picked.Values.ToList();
        }
        else if (NeedsValue)
        {
            read["value"] = number ? Number(_value, "Value") : _value;
        }
        return read;
    }

    private string StartOp() => ColumnTypes.Family(TypeOf(_column)) is "text" or "number" ? "in" : Conditions[0].Op;

    private async Task ColumnChangedAsync(ChangeEventArgs e)
    {
        _column = e.Value?.ToString() ?? string.Empty;
        _picked.Clear();
        _search = string.Empty;
        _op = StartOp();
        await LoadValuesAsync();
    }

    private Task OpChangedAsync(ChangeEventArgs e)
    {
        _op = e.Value?.ToString() ?? "eq";
        return LoadValuesAsync();
    }

    private Task SearchAsync() => LoadValuesAsync();

    private async Task LoadValuesAsync()
    {
        if (!IsList || _column.Length == 0)
        {
            return;
        }
        var mine = ++_asked;
        try
        {
            var found = await Grids.ValuesAsync(Grid, _column, _search, Index);
            if (mine == _asked)
            {
                _values = found;
            }
        }
        catch (ApiException)
        {
            _values = new ValueList(); // the server could not list them: the value box still works
        }
    }

    private void Pick(JsonElement value, bool on)
    {
        if (on)
        {
            _picked[value.GetRawText()] = value.Clone();
        }
        else
        {
            _picked.Remove(value.GetRawText());
        }
    }

    private static string Words(JsonElement value) => value.ValueKind switch
    {
        JsonValueKind.String => value.GetString() is { Length: > 0 } text ? text : "(empty text)",
        _ => value.GetRawText(),
    };
}
