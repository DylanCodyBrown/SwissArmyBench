using System.Globalization;
using System.Text.Json;

using Microsoft.AspNetCore.Components;

using SwissArmyBench.Web.Api;
using SwissArmyBench.Web.Api.Grids;

namespace SwissArmyBench.Web.Pages.Grids.Profile;

public partial class ColumnProfileDialog
{
    private string _column = string.Empty;
    private ColumnProfile? _profile;
    private Exception? _error;

    [Inject]
    private GridsClient Grids { get; set; } = default!;

    [Parameter, EditorRequired]
    public string Grid { get; set; } = string.Empty;

    [Parameter, EditorRequired]
    public string Column { get; set; } = string.Empty;

    /// <summary>The columns the picker offers (the view's, or a previewed step's).</summary>
    [Parameter, EditorRequired]
    public IReadOnlyList<string> Columns { get; set; } = [];

    /// <summary>A step's preview: the column after that many steps.</summary>
    [Parameter]
    public int? Upto { get; set; }

    /// <summary>A value clicked: a filter step to it, made by the page ({column, op, ...}).</summary>
    [Parameter]
    public EventCallback<object> OnFilter { get; set; }

    /// <summary>Send to Analyze: the column shown.</summary>
    [Parameter]
    public EventCallback<string> OnSend { get; set; }

    [Parameter]
    public EventCallback OnClose { get; set; }

    protected override Task OnInitializedAsync() => ShowAsync(Column);

    private async Task ShowAsync(string column)
    {
        _column = column;
        _profile = null;
        _error = null;
        try
        {
            _profile = await Grids.ProfileAsync(Grid, column, Upto);
        }
        catch (ApiException error)
        {
            _error = error;
        }
    }

    /// <summary>The tiles: every column's four, then its family's.</summary>
    private static IEnumerable<(string Label, string Value)> Tiles(ColumnProfile p)
    {
        yield return ("Rows", ProfileWords.Of(p.Rows));
        yield return ("Blank", $"{p.Blanks:N0} ({p.BlankPercent.ToString(CultureInfo.CurrentCulture)}%)");
        yield return ("Distinct", ProfileWords.Of(p.Distinct));
        yield return ("All unique", p.AllUnique ? "yes" : "no");
        var family = p.Family switch
        {
            "number" => new (string, string)[]
            {
                ("Min", ProfileWords.Of(p.Min)), ("Max", ProfileWords.Of(p.Max)), ("Mean", ProfileWords.Of(p.Mean)), ("Median", ProfileWords.Of(p.Median)),
                ("1st quartile", ProfileWords.Of(p.Q1)), ("3rd quartile", ProfileWords.Of(p.Q3)), ("Std deviation", ProfileWords.Of(p.Stddev)),
                ("Sum", ProfileWords.Of(p.Sum)), ("Zeros", ProfileWords.Of(p.Zeros)), ("Negatives", ProfileWords.Of(p.Negatives)),
            },
            "text" => [("Shortest", ProfileWords.Of(p.Shortest)), ("Longest", ProfileWords.Of(p.Longest)), ("Empty text", ProfileWords.Of(p.EmptyStrings)), ("Padded spaces", ProfileWords.Of(p.Padded))],
            "date" or "timestamp" => [("Earliest", ProfileWords.Of(p.Earliest)), ("Latest", ProfileWords.Of(p.Latest))],
            _ => [],
        };
        foreach (var tile in family)
        {
            yield return tile;
        }
    }

    private static string Height(long count, long tallest) => FormattableString.Invariant($"height: {100.0 * count / tallest:0.##}%");

    private static string Share(long count, long top) => FormattableString.Invariant($"--share: {100.0 * count / top:0.##}%");

    /// <summary>A value's filter (the classic filterOn): blank, a day for a date, true or false, else equals.</summary>
    private Task FilterOnAsync(JsonElement value)
    {
        var family = _profile?.Family ?? string.Empty;
        object step = value.ValueKind switch
        {
            JsonValueKind.Null or JsonValueKind.Undefined => new { column = _column, op = "blank" },
            _ when family is "date" or "timestamp" => new { column = _column, op = "date_between", low = Day(value), high = Day(value) },
            JsonValueKind.True or JsonValueKind.False when family == "boolean" => new { column = _column, op = value.GetBoolean() ? "true" : "false" },
            _ => new { column = _column, op = "eq", value },
        };
        return OnFilter.InvokeAsync(step);
    }

    private static string Day(JsonElement value)
    {
        var text = value.ValueKind == JsonValueKind.String ? value.GetString() ?? string.Empty : value.GetRawText();
        return text.Length >= 10 ? text[..10] : text;
    }
}
