using System.Text.Json;

using SwissArmyBench.Web.Api.Grids;

namespace SwissArmyBench.Web.Pages.Grids;

/// <summary>
/// The table in front as the screen state's `table` part (State/ScreenState; the server's domain/screen.py): its
/// name, columns, steps, selection and the rows on screen. Names and numbers only: a step says its kind and the
/// columns it names, never the value it filters by; the selection says rows and columns by number, never a cell.
/// </summary>
public static class TableScreen
{
    public static Dictionary<string, object?> Of(GridInfo info, GridSelection selection, long rows, (long First, long Last) onScreen) => new()
    {
        ["grid"] = info.Grid,
        ["name"] = info.Dataset,
        ["title"] = info.Title,
        ["rows"] = rows,
        ["columns"] = info.Columns.Select(c => new Dictionary<string, object?> { ["name"] = c.Name, ["type"] = c.Type }).ToList(),
        ["steps"] = info.Steps.Select(Step).ToList(),
        ["selection"] = Selection(info, selection, rows),
        ["showing"] = rows > 0 ? new Dictionary<string, object?> { ["first"] = Math.Min(onScreen.First + 1, rows), ["last"] = Math.Min(onScreen.Last + 1, rows) } : null,
    };

    /// <summary>A step by its kind, whether it is on, a filter's test and the columns it names.</summary>
    public static Dictionary<string, object?> Step(GridStep step)
    {
        var named = step.Params.ValueKind == JsonValueKind.Object ? step.Params : default;
        List<string> columns = [];
        List<string> directions = [];
        foreach (var key in new[] { "column", "columns", "keep", "keys", "as" })
        {
            if (named.ValueKind != JsonValueKind.Object || !named.TryGetProperty(key, out var value))
            {
                continue;
            }
            if (value.ValueKind == JsonValueKind.String)
            {
                columns.Add(value.GetString() ?? string.Empty);
            }
            foreach (var item in value.ValueKind == JsonValueKind.Array ? value.EnumerateArray() : [])
            {
                // A sort's key is [column, direction]; every other list is of names.
                var name = item.ValueKind == JsonValueKind.Array && item.GetArrayLength() > 0 ? item[0] : item;
                if (name.ValueKind == JsonValueKind.String)
                {
                    columns.Add(name.GetString() ?? string.Empty);
                }
                if (item.ValueKind == JsonValueKind.Array && item.GetArrayLength() > 1 && item[1].ValueKind == JsonValueKind.String)
                {
                    directions.Add(item[1].GetString() ?? string.Empty);
                }
            }
        }
        if (named.ValueKind == JsonValueKind.Object && named.TryGetProperty("mapping", out var mapping) && mapping.ValueKind == JsonValueKind.Object)
        {
            columns.AddRange(mapping.EnumerateObject().Select(renamed => renamed.Name));
        }
        return new()
        {
            ["kind"] = step.Kind,
            ["enabled"] = step.Enabled,
            ["op"] = step.Kind == "filter" && named.ValueKind == JsonValueKind.Object && named.TryGetProperty("op", out var op) && op.ValueKind == JsonValueKind.String ? op.GetString() : null,
            ["columns"] = columns,
            ["directions"] = directions.Count > 0 ? directions : null,
        };
    }

    /// <summary>The selection by number: row ranges from 1 as the grid counts them, columns by name and by place.</summary>
    private static Dictionary<string, object?> Selection(GridInfo info, GridSelection selection, long rows)
    {
        var names = selection.Descriptor?.Columns ?? (selection.Kind == "none" ? selection.Target : []);
        var places = info.Columns.Select((c, at) => (c.Name, Place: at + 1)).ToDictionary(c => c.Name, c => c.Place, StringComparer.Ordinal);
        var ranges = selection.Descriptor?.Rows ?? (selection.Kind is "all" or "columns" && rows > 0 ? [[0, rows - 1]] : []);
        return new()
        {
            ["kind"] = selection.Kind,
            ["rows"] = ranges.Where(r => r.Length == 2).Select(r => new Dictionary<string, object?> { ["first"] = r[0] + 1, ["last"] = r[1] + 1 }).ToList(),
            ["columns"] = names,
            ["column_numbers"] = names.Where(places.ContainsKey).Select(n => places[n]).ToList(),
        };
    }
}
