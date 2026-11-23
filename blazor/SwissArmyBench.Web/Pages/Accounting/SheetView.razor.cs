using System.Globalization;

using Microsoft.AspNetCore.Components;
using Microsoft.JSInterop;

using SwissArmyBench.Web.Api.Accounting;

namespace SwissArmyBench.Web.Pages.Accounting;

public partial class SheetView
{
    // A sheet shows at least this many columns; Excel's own width is 8.43 characters (7 pixels each, and 5 more).
    private const int MinColumns = 8;
    private const double DefaultWidth = 8.43;
    private const double PixelsPerChar = 7;
    private const double WidthPadding = 5;

    // A cell's words are no larger than this on the page (a title's 16 points and up).
    private const double MaxFont = 22;

    private readonly HashSet<(int, int)> _covered = [];
    private readonly Dictionary<(int, int), (int Rows, int Columns)> _spans = [];
    private readonly Dictionary<string, string> _named = [];
    private ElementReference _wrap;
    private IJSObjectReference? _module;

    [Parameter, EditorRequired]
    public PreviewSheet Sheet { get; set; } = default!;

    [Parameter]
    public IReadOnlyDictionary<string, string>? Names { get; set; }

    /// <summary>Cells to mark (a template's bound places), by address or named range: their words.</summary>
    [Parameter]
    public IReadOnlyDictionary<string, string>? Marks { get; set; }

    /// <summary>A cell clicked: its address and the named range there, if any.</summary>
    [Parameter]
    public EventCallback<(string Cell, string? Named)> OnPick { get; set; }

    private int Columns => Math.Max(Sheet.Rows.Select(r => r.Count).Append(0).Max(), MinColumns);

    protected override void OnParametersSet()
    {
        _covered.Clear();
        _spans.Clear();
        foreach (var range in Sheet.Merged)
        {
            var parts = range.Split(':');
            if (parts.Length != 2)
            {
                continue;
            }
            var (r1, c1) = WorkbookRules.CellAt(parts[0]);
            var (r2, c2) = WorkbookRules.CellAt(parts[1]);
            _spans[(r1, c1)] = (r2 - r1 + 1, c2 - c1 + 1);
            for (var r = r1; r <= r2; r++)
            {
                for (var c = c1; c <= c2; c++)
                {
                    if (r != r1 || c != c1)
                    {
                        _covered.Add((r, c));
                    }
                }
            }
        }
        _named.Clear();
        foreach (var (name, place) in Names ?? new Dictionary<string, string>())
        {
            var parts = place.Split('!');
            var (where, reference) = parts.Length > 1 ? (parts[0].Trim('\''), parts[1]) : (Sheet.Name, place);
            if (where == Sheet.Name && reference.Length > 0)
            {
                _named[reference.Split(':')[0].Replace("$", string.Empty, StringComparison.Ordinal).ToUpperInvariant()] = name;
            }
        }
    }

    protected override async Task OnAfterRenderAsync(bool firstRender)
    {
        if (Sheet.Charts.Count > 0)
        {
            _module ??= await Js.InvokeAsync<IJSObjectReference>("import", "./js/workbook.js");
            await _module.InvokeVoidAsync("placeCharts", _wrap);
        }
    }

    private string ColumnWidth(int column) =>
        Math.Round((Sheet.Widths.GetValueOrDefault(WorkbookRules.Letters(column), DefaultWidth) * PixelsPerChar) + WidthPadding).ToString(CultureInfo.InvariantCulture);

    private string? CellClass(PreviewCell? cell, string? mark, string? named)
    {
        var classes = new[]
        {
            cell?.N is not null ? "num" : null,
            cell?.B is not null ? "b" : null,
            cell?.I is not null ? "i" : null,
            cell?.Top is not null ? "top" : null,
            cell?.Bottom is not null ? "bottom" : null,
            mark is not null ? "bound" : null,
            named is not null ? "named" : null,
        }.OfType<string>().ToList();
        return classes.Count > 0 ? string.Join(' ', classes) : null;
    }

    private static string? Titled(PreviewCell? cell, string? named, string? mark)
    {
        var parts = new[] { cell?.Formula, named, mark }.Where(p => !string.IsNullOrEmpty(p)).ToList();
        return parts.Count > 0 ? string.Join(" · ", parts) : null;
    }

    private static string? CellStyle(PreviewCell? cell)
    {
        var parts = new[]
        {
            Hex(cell?.Fill) is { } fill ? $"background: {fill}" : null,
            Hex(cell?.C) is { } colour ? $"color: {colour}" : null,
            cell?.Size is { } size ? string.Create(CultureInfo.InvariantCulture, $"font-size: {Math.Min(MaxFont, size)}px") : null,
        }.OfType<string>().ToList();
        return parts.Count > 0 ? string.Join("; ", parts) : null;
    }

    /// <summary>A colour as #RGB or #RRGGBB(AA) only: a cell's colour never becomes more of the style.</summary>
    private static string? Hex(string? colour) =>
        colour is not null && System.Text.RegularExpressions.Regex.IsMatch(colour, "^#[0-9A-Fa-f]{3,8}$") ? colour : null;

    private Task PickAsync(string cell, string? named) => OnPick.HasDelegate ? OnPick.InvokeAsync((cell, named)) : Task.CompletedTask;

    public async ValueTask DisposeAsync()
    {
        if (_module is not null)
        {
            try
            {
                await _module.DisposeAsync();
            }
            catch (JSDisconnectedException)
            {
                // The page is going.
            }
        }
    }
}
