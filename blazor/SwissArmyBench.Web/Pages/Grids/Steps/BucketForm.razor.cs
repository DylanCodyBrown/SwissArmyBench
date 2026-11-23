using System.Globalization;
using System.Text.Json;

using Microsoft.AspNetCore.Components;

using SwissArmyBench.Web.Api;
using SwissArmyBench.Web.Api.Grids;

namespace SwissArmyBench.Web.Pages.Grids.Steps;

public partial class BucketForm
{
    // About this many buckets across the column's range when the width is not given.
    private const double BucketsAcross = 10;
    private const string Suffix = "_bucket";

    private string _column = string.Empty;
    private string _as = string.Empty;
    private string _mode = "width";
    private string _unit = "month";
    private string _edges = string.Empty;
    private string _width = string.Empty;
    private string _low = string.Empty;
    private string _high = string.Empty;
    private bool _rightClosed;
    private string _other = "Other";

    [Inject]
    private GridsClient Grids { get; set; } = default!;

    private IEnumerable<GridColumn> Usable => Columns.Where(c => ColumnTypes.IsNumber(c.Type) || ColumnTypes.IsDate(c.Type));

    protected override async Task OnInitializedAsync()
    {
        _column = Text("column", Usable.FirstOrDefault()?.Name ?? string.Empty);
        _as = Text("as");
        _mode = Text("mode", _mode);
        _unit = Text("unit", _unit);
        _width = Raw("width");
        _low = Raw("low");
        _high = Raw("high");
        _edges = string.Join(", ", Items("edges").Select(e => e.GetRawText()));
        _rightClosed = Flag("right_closed");
        _other = Text("other_label", _other);
        await FollowColumnAsync();
    }

    public override Dictionary<string, object?> Read()
    {
        var read = new Dictionary<string, object?> { ["column"] = _column, ["as"] = _as.Trim(), ["mode"] = _mode };
        if (_mode == "date")
        {
            read["unit"] = _unit;
            return read;
        }
        if (_mode == "width")
        {
            read["width"] = Number(_width, "Width");
            read["low"] = Number(_low, "From");
            read["high"] = Number(_high, "To");
        }
        else
        {
            read["edges"] = _edges.Split(',', StringSplitOptions.RemoveEmptyEntries).Select(e => Number(e, "Edges")).ToList();
        }
        read["right_closed"] = _rightClosed;
        read["other_label"] = _other;
        return read;
    }

    private async Task ColumnChangedAsync(ChangeEventArgs e)
    {
        _column = e.Value?.ToString() ?? string.Empty;
        _low = string.Empty;
        _high = string.Empty;
        _width = string.Empty;
        await FollowColumnAsync();
    }

    private Task ModeChangedAsync(ChangeEventArgs e)
    {
        _mode = e.Value?.ToString() ?? "width";
        return FollowColumnAsync();
    }

    /// <summary>A date column buckets by a unit; the new column's name follows the column; a width's range starts
    /// from the column's own smallest and largest values.</summary>
    private async Task FollowColumnAsync()
    {
        if (ColumnTypes.IsDate(TypeOf(_column)))
        {
            _mode = "date";
        }
        if (_as.Length == 0 || _as.EndsWith(Suffix, StringComparison.Ordinal))
        {
            _as = _column + Suffix;
        }
        if (_mode != "width" || (_low.Length > 0 && _high.Length > 0) || _column.Length == 0)
        {
            return;
        }
        try
        {
            var profile = await Grids.ProfileAsync(Grid, _column);
            if (profile.Min is { ValueKind: JsonValueKind.Number } min && profile.Max is { ValueKind: JsonValueKind.Number } max)
            {
                var low = min.GetDouble();
                var high = max.GetDouble();
                _low = Math.Floor(low).ToString(CultureInfo.InvariantCulture);
                _high = (Math.Ceiling(high) + (high == Math.Floor(high) ? 1 : 0)).ToString(CultureInfo.InvariantCulture);
                if (_width.Length == 0)
                {
                    _width = Math.Max(1, Math.Ceiling((high - low) / BucketsAcross)).ToString(CultureInfo.InvariantCulture);
                }
            }
        }
        catch (ApiException)
        {
            // No profile: the user types the range.
        }
    }
}
