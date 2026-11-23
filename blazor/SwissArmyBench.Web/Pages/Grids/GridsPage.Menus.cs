using System.Globalization;
using System.Text.Json;

using Microsoft.JSInterop;

using SwissArmyBench.Web.Components;

namespace SwissArmyBench.Web.Pages.Grids;

/// <summary>The grid's right-click menus (the classic cellMenu.ts): a cell's (send it or its row to Analyze, Keep
/// these, Exclude these, View value, the three copies) and a header's (the column's tools, then the analyses).</summary>
public partial class GridsPage
{
    // ===== the right-click menus (the classic cellMenu.ts) =====

    private void CellMenu(GridPoint at) => _menu = new OpenMenu(CellWhere(at), CellEntries(at), at.X, at.Y);

    private static string CellWhere(GridPoint at) =>
        $"{at.Column}, row {(at.Row + 1).ToString("N0", CultureInfo.InvariantCulture)}";

    /// <summary>The cell in front: the first cell of the selection, or null (the palette's Cell commands say
    /// "Click a cell first").</summary>
    private GridPoint? SelectedCell =>
        _selection.Descriptor is { Rows: [var rows, ..], Columns: [var column, ..] } && rows.Length > 0
            ? new GridPoint(rows[0], column, 0, 0)
            : null;

    /// <summary>What a cell's right-click menu offers, the palette's Cell group too.</summary>
    private List<MenuEntry> CellEntries(GridPoint at)
    {
        var where = CellWhere(at);
        return
        [
            new("Send value to Analyze", "image", () => SendValueAsync(at, where)),
            new("Send the row to Analyze", "rows", () => SendRowAsync(at.Row)),
            MenuEntry.Separator,
            new("Keep these", "filter", () => FilterByCellsAsync(at.Column, keep: true)),
            new("Exclude these", "exclude", () => FilterByCellsAsync(at.Column, keep: false)),
            MenuEntry.Separator,
            new("View value", "eye", () => ViewCellAsync(at)),
            new("Copy", "copy", () => CopyAsync("plain")),
            new("Copy with headers", "copy", () => CopyAsync("headers")),
            new("Copy as Markdown", "copy", () => CopyAsync("markdown")),
        ];
    }

    /// <summary>A header's menu: the column's own tools (on every selected column when it is one of them), then the
    /// analyses. A LIST or STRUCT column also unnests.</summary>
    private void HeaderMenu(GridPoint at)
    {
        var columns = Target.Contains(at.Column) ? Target : [at.Column];
        var type = TypeOf(at.Column);
        var nested = type.EndsWith(']') || type.StartsWith("STRUCT", StringComparison.OrdinalIgnoreCase) || type.StartsWith("LIST", StringComparison.OrdinalIgnoreCase);
        List<MenuEntry> entries =
        [
            new("Sort A→Z", "sortup", () => SortAsync(columns, "asc")),
            new("Sort Z→A", "sortdown", () => SortAsync(columns, "desc")),
            new("Filter…", "filter", () => Open("filter", new { column = at.Column })),
            new("Rename…", "rename", () => Open("rename", new { only = columns })),
            new("Remove", "trash", () => KeepColumnsAsync(AllColumns().Where(c => !columns.Contains(c)).ToList())),
            new("Keep only", "columns", () => KeepColumnsAsync(columns)),
            new("Group by…", "group", () => Open("group_by", new { keys = columns })),
        ];
        if (nested)
        {
            entries.Add(new("Unnest this column", "rows", () => UnnestAsync(at.Column)));
        }
        entries.AddRange(
        [
            MenuEntry.Separator,
            new("Profile to Analyze", "image", () => ProfileToAnalyzeAsync(at.Column)),
            new("Distinct values to Analyze", "tag", () => DistinctToAnalyzeAsync(at.Column)),
            new("Profile…", "profile", () => ShowProfile(at.Column)),
        ]);
        _menu = new OpenMenu(at.Column, entries, at.X, at.Y);
    }

    private Task Open(string kind, object preset)
    {
        OpenEditor(kind, preset);
        return Task.CompletedTask;
    }

    private Task ShowProfile(string column)
    {
        OpenProfile(column);
        return Task.CompletedTask;
    }

    private async Task CopyAsync(string style)
    {
        if (_grid is null)
        {
            return;
        }
        try
        {
            if (await _grid.CopyAsync(style) is { } words)
            {
                _ = Notes.SayAsync(words);
            }
        }
        catch (JSException error)
        {
            _ = Notes.SayAsync($"Could not copy: {error.Message}");
        }
    }

    /// <summary>Keep (or exclude) the rows whose value in the column is one of the selected cells' values.</summary>
    private async Task FilterByCellsAsync(string column, bool keep)
    {
        if (_grid is null)
        {
            return;
        }
        var values = (await _grid.ValuesAsync(column)).Take(MostValues).ToList();
        var present = values.Where(v => v.ValueKind is not JsonValueKind.Null and not JsonValueKind.Undefined).ToList();
        object parameters;
        if (present.Count == 0)
        {
            parameters = new { column, op = keep ? "blank" : "not_blank" };
        }
        else if (present.Count == 1 && present[0].ValueKind is JsonValueKind.True or JsonValueKind.False)
        {
            parameters = new { column, op = keep == present[0].GetBoolean() ? "true" : "false" };
        }
        else if (present.Count == 1)
        {
            parameters = new { column, op = keep ? "eq" : "ne", value = present[0] };
        }
        else
        {
            parameters = new { column, op = keep ? "in" : "not_in", values = present };
        }
        if (present.Count > 0 && present.Count < values.Count)
        {
            _ = Notes.SayAsync("Blank cells left out of the filter.");
        }
        await AddStepAsync(("filter", parameters));
    }
}
