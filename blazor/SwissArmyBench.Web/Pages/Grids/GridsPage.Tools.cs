using System.Globalization;
using System.Text.Json;

using SwissArmyBench.Web.Api;
using SwissArmyBench.Web.Api.Grids;

namespace SwissArmyBench.Web.Pages.Grids;

/// <summary>
/// The Grids page's tools (the classic ribbon.ts, cellMenu.ts and stepForms.ts's editStep): what each ribbon button
/// and menu line does. Every change lands as a step (filter, sort, columns...), so it can be turned off, edited and
/// exported like any other.
/// </summary>
public partial class GridsPage
{
    // A filter list should stay short: the selection's values are read from the loaded rows, up to this many.
    private const int MostValues = 500;

    private GridSelection _selection = GridSelection.None;
    private StepRequest? _editor;
    private string? _dialog;
    private OpenMenu? _menu;
    private TableConnection? _connection;
    private int _statsAsked;
    private long _selectedRows;

    private string ConnectionLabel => _connection switch
    {
        null => "Connection…",
        { Connection: { } name } => $"Connection: {name}",
        { How: "query" } => "Connection: Query",
        _ => "Connection…",
    };

    /// <summary>The columns entering a step: an edited step offers what it sees, a new one the view's.</summary>
    private IReadOnlyList<GridColumn> EnteringColumns(int? index)
    {
        var stages = _info?.StageColumns;
        if (index is { } at && stages is { Count: > 0 })
        {
            return stages[Math.Min(at, stages.Count - 1)];
        }
        return _info?.Columns ?? [];
    }

    private IReadOnlyList<string> Target => _selection.Target;

    private async Task RunToolAsync(string tool)
    {
        if (_info is not { } info)
        {
            return;
        }
        var target = Target;
        var one = target.Count == 1 ? target[0] : null;
        switch (tool)
        {
            case "matching" or "export" or "profile" or "keyfinder" or "connection" or "code":
                _dialog = tool;
                break;
            case "filter":
                OpenEditor("filter", target.Count > 0 ? new { column = target[0] } : null);
                break;
            case "distinct":
                await AddStepAsync(("distinct", new Dictionary<string, object>()));
                break;
            case "sort" or "columns" or "rename" or "group_by" or "limit" or "transform":
                OpenEditor(tool, null);
                break;
            case "autowidth":
                await AutoSizeAsync([]);
                break;
            case "relationships":
                _dialog = tool;
                break;
            case "variant":
                await MakeVariantAsync(info.Dataset);
                break;
            default:
                await RunColumnToolAsync(tool, target, one);
                break;
        }
    }

    /// <summary>The Column row's tools, on the selected columns (or the clicked cell's).</summary>
    private async Task RunColumnToolAsync(string tool, IReadOnlyList<string> target, string? one)
    {
        switch (tool)
        {
            case "col-sort-asc":
                await SortAsync(target, "asc");
                break;
            case "col-sort-desc":
                await SortAsync(target, "desc");
                break;
            case "col-filter":
                OpenEditor("filter", new { column = one });
                break;
            case "col-rename":
                OpenEditor("rename", new { only = target });
                break;
            case "col-autowidth":
                await AutoSizeAsync(target);
                break;
            case "col-remove":
                await KeepColumnsAsync(AllColumns().Where(c => !target.Contains(c)).ToList());
                break;
            case "col-keep":
                await KeepColumnsAsync(target);
                break;
            case "col-clean":
                OpenEditor("transform", new { columns = target.Where(c => ColumnTypes.IsText(TypeOf(c))).ToList() });
                break;
            case "col-bucket":
                OpenEditor("bucket", new { column = one });
                break;
            case "col-categorize":
                OpenEditor("categorize", new { column = one });
                break;
            case "col-group":
                OpenEditor("group_by", new { keys = target });
                break;
            case "col-profile" when one is not null:
                OpenProfile(one);
                break;
            default:
                break;
        }
    }

    private void OpenEditor(string kind, object? preset)
    {
        var start = preset is null ? JsonSerializer.SerializeToElement(new Dictionary<string, object>()) : JsonSerializer.SerializeToElement(preset, ApiClient.Json);
        _editor = new StepRequest(kind, start, null);
    }

    private void EditStep(int index)
    {
        if (_info?.Steps is { } steps && index < steps.Count)
        {
            _editor = new StepRequest(steps[index].Kind, steps[index].Params, index);
        }
    }

    private const string StepsPanel = "steps";

    private int? _previewUpto;

    private void CloseDialog() => _dialog = null;

    /// <summary>A step's data previewed in the grid (0: the source), or the full view again (null).</summary>
    private Task PreviewAsync(int? upto)
    {
        _previewUpto = upto;
        Status.SetPreview(upto);
        return Task.CompletedTask;
    }

    private void EditFromPanel((string Kind, int? Index) edit)
    {
        if (edit.Index is { } index)
        {
            EditStep(index);
        }
        else
        {
            OpenEditor(edit.Kind, null);
        }
    }

    private Task ReorderStepsAsync(IReadOnlyList<GridStep> steps) => ChangedAsync(() => Grids.SaveStepsAsync(_active!, steps));

    private IReadOnlyList<string> AllColumns() => _info?.Columns.Select(c => c.Name).ToList() ?? [];

    /// <summary>A step's editor saved: a new step at the end, or the edited one in its place.</summary>
    private async Task SaveStepAsync(Dictionary<string, object?> parameters)
    {
        if (_editor is not { } editor || _info is not { } info)
        {
            return;
        }
        if (editor.Index is { } index)
        {
            var edited = JsonSerializer.SerializeToElement(parameters, ApiClient.Json);
            var steps = info.Steps.Select((step, at) => at == index ? step with { Params = edited } : step).ToList();
            await ChangedOrThrowAsync(() => Grids.SaveStepsAsync(info.Grid, steps));
            return;
        }
        await ChangedOrThrowAsync(() => Grids.AddStepAsync(info.Grid, editor.Kind, parameters));
    }

    private Task SaveMatchingAsync(TextMatching settings) =>
        ChangedOrThrowAsync(() => Grids.SaveStepsAsync(_info!.Grid, _info.Steps, settings));

    /// <summary>A change whose refusal the caller shows in place (a step's editor, the matching dialog).</summary>
    private async Task ChangedOrThrowAsync(Func<Task<GridInfo>> change)
    {
        _info = await change();
        if (_grid is not null)
        {
            await _grid.RefreshAsync(_info.Columns);
        }
        _tabs = await Grids.ListAsync();
        StateHasChanged();
    }

    /// <summary>A header renamed in place: a rename step.</summary>
    private Task RenameColumnAsync((string Column, string To) rename) =>
        AddStepAsync(("rename", new { mapping = new Dictionary<string, string> { [rename.Column] = rename.To } }));

    private Task SortAsync(IReadOnlyList<string> columns, string direction) =>
        AddStepAsync(("sort", new { keys = columns.Select(c => new[] { c, direction }).ToList() }));

    private async Task KeepColumnsAsync(IReadOnlyList<string> keep)
    {
        if (keep.Count == 0)
        {
            _ = Notes.SayAsync("That would remove every column.");
            return;
        }
        var gone = AllColumns().Where(c => !keep.Contains(c)).ToList();
        await AddStepAsync(("columns", new { keep }));
        if (gone.Count > 0 && _error is null)
        {
            UndoNote(gone.Count == 1 ? $"Removed the column {gone[0]}" : $"Removed {gone.Count} columns");
        }
    }

    private async Task AutoSizeAsync(IReadOnlyList<string> columns)
    {
        if (_grid is not null)
        {
            await _grid.AutoSizeAsync(columns);
        }
    }

    private async Task MakeVariantAsync(string dataset)
    {
        try
        {
            var made = await Grids.SandboxVariantAsync(dataset);
            _ = Notes.SayAsync($"In the project's sandbox: {made.Title ?? made.Added ?? dataset}.");
        }
        catch (ApiException error)
        {
            _error = error;
        }
    }

    private async Task LoadConnectionAsync()
    {
        if (_info is not { } info)
        {
            return;
        }
        try
        {
            _connection = await Grids.ConnectionOfAsync(info.Dataset);
        }
        catch (ApiException)
        {
            _connection = null; // the label says Connection… and the dialog asks again
        }
    }

    // ===== the selection and its numbers =====

    private async Task SelectionChangedAsync(GridSelection selection)
    {
        _selection = selection;
        var mine = ++_statsAsked;
        if (selection.Descriptor is not { } descriptor || _active is null)
        {
            Status.Set(null);
            return;
        }
        try
        {
            var stats = await Grids.SelectionStatsAsync(_active, descriptor);
            if (mine == _statsAsked)
            {
                Status.Set(StatsWords(selection.Kind, stats));
                _selectedRows = stats.Rows;
            }
        }
        catch (ApiException)
        {
            // The status bar keeps its last numbers.
        }
    }

    /// <summary>Excel's status bar (the classic bottomBar.ts): what is selected, Count (non-blank cells), then Average
    /// and Sum over the number cells to the columns' scale (an identifier column is counted only).</summary>
    private static string StatsWords(string kind, SelectionStats stats)
    {
        var what = kind switch
        {
            "rows" => $"{stats.Rows.ToString("N0", CultureInfo.CurrentCulture)} row{(stats.Rows == 1 ? string.Empty : "s")} selected",
            "all" => "All selected",
            _ => $"{stats.Cells.ToString("N0", CultureInfo.CurrentCulture)} cell{(stats.Cells == 1 ? string.Empty : "s")} selected",
        };
        var words = new List<string> { what, $"Count {stats.Count.ToString("N0", CultureInfo.CurrentCulture)}" };
        if (stats.Mean is { } mean && stats.Sum is { } sum)
        {
            words.Add($"Average {Scaled(mean, Digits(stats, "mean"))}");
            words.Add($"Sum {Scaled(sum, Digits(stats, "sum"))}");
        }
        return string.Join(" · ", words);
    }

    private static int Digits(SelectionStats stats, string name) =>
        stats.Digits is { ValueKind: JsonValueKind.Object } digits && digits.TryGetProperty(name, out var d) && d.ValueKind == JsonValueKind.Number ? d.GetInt32() : 2;

    /// <summary>A number with `digits` after the point, grouped; a small fraction keeps four significant digits.</summary>
    private static string Scaled(double value, int digits)
    {
        if (value != 0 && Math.Abs(value) < 1 && digits > 0 && Math.Abs(value) < Math.Pow(10, -digits) * 10)
        {
            return value.ToString("G4", CultureInfo.CurrentCulture);
        }
        return value.ToString($"N{digits}", CultureInfo.CurrentCulture);
    }

    private void Say(string words) => _ = Notes.SayAsync(words);
}
