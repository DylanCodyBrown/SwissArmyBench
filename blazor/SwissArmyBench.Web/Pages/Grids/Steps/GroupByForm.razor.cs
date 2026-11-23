using System.Text.Json;

namespace SwissArmyBench.Web.Pages.Grids.Steps;

public partial class GroupByForm
{
    private static readonly (string Fn, string Words)[] _functions =
    [
        ("count_rows", "count of rows"), ("count", "count of non-blank"), ("distinct_count", "distinct count"),
        ("sum", "sum"), ("mean", "mean"), ("min", "min"), ("max", "max"),
    ];

    private readonly HashSet<string> _keys = [];
    private readonly List<AggregateRow> _rows = [];

    protected override void OnInitialized()
    {
        _keys.UnionWith(Names("keys"));
        foreach (var given in Items("aggregates").Where(a => a.ValueKind == JsonValueKind.Object))
        {
            _rows.Add(new AggregateRow
            {
                Fn = given.TryGetProperty("fn", out var fn) ? fn.GetString() ?? "count_rows" : "count_rows",
                Column = given.TryGetProperty("column", out var column) ? column.GetString() ?? FirstColumn : FirstColumn,
                As = given.TryGetProperty("as", out var name) ? name.GetString() ?? string.Empty : string.Empty,
            });
        }
        if (_rows.Count == 0)
        {
            _rows.Add(new AggregateRow { Column = FirstColumn });
        }
    }

    private string FirstColumn => Columns.FirstOrDefault()?.Name ?? string.Empty;

    public override Dictionary<string, object?> Read()
    {
        var keys = Columns.Select(c => c.Name).Where(_keys.Contains).ToList();
        if (keys.Count == 0)
        {
            throw new StepFormException("Tick a column to group by.");
        }
        var aggregates = _rows.Select(row =>
        {
            var one = new Dictionary<string, object?> { ["fn"] = row.Fn };
            if (row.Fn != "count_rows")
            {
                one["column"] = row.Column;
            }
            if (row.As.Trim().Length > 0)
            {
                one["as"] = row.As.Trim();
            }
            return one;
        }).ToList();
        return new() { ["keys"] = keys, ["aggregates"] = aggregates };
    }

    private void Key(string name, bool on)
    {
        if (on)
        {
            _keys.Add(name);
        }
        else
        {
            _keys.Remove(name);
        }
    }

    private void AddRow() => _rows.Add(new AggregateRow { Fn = "sum", Column = FirstColumn });
}
