using System.Globalization;
using System.Net;
using System.Text;

using SwissArmyBench.Web.Api.Accounting;

namespace SwissArmyBench.Web.Pages.Accounting;

/// <summary>A built chart as a picture of itself (the classic excelPreview.ts chartPicture): what Excel draws from the
/// same series, columns, bars, lines, a pie, a combo's lines over its columns, its title and legend. Every word is
/// escaped: a workbook's cells are data, never markup.</summary>
public static class ChartSvg
{
    // Pixels in a centimetre (a chart's size in the workbook), and the picture's least size.
    private const double Cm = 37.8;
    private const int MinW = 220;
    private const int MinH = 140;

    // The plot's margins: the ticks' room on the left, the legend's row, the title's room.
    private const int Left = 46;
    private const int RightPad = 14;
    private const int LegendH = 20;
    private const int TitleRoom = 30;
    private const int NoTitleRoom = 12;
    private const int AxisRoom = 34;

    // A category's words are cut past this many characters.
    private const int MaxCategory = 14;

    private static readonly string[] _palette = ["#1f3864", "#c55a11", "#548235", "#7030a0", "#2e75b6", "#bf9000"];

    public static string Colour(int i) => _palette[i % _palette.Length];

    public static string Draw(PreviewChart chart)
    {
        var w = Math.Max(MinW, (int)Math.Round(chart.Width * Cm));
        var h = Math.Max(MinH, (int)Math.Round(chart.Height * Cm));
        var svg = new StringBuilder();
        var label = $"{chart.Kind} chart{(chart.Title is { Length: > 0 } t ? ": " + t : string.Empty)}";
        svg.Append(Inv($"<svg xmlns=\"http://www.w3.org/2000/svg\" viewBox=\"0 0 {w} {h}\" width=\"{w}\" height=\"{h}\" class=\"xc-chart\" role=\"img\" aria-label=\"{Esc(label)}\">"));
        svg.Append(Inv($"<rect x=\"0\" y=\"0\" width=\"{w}\" height=\"{h}\" class=\"xc-chart-frame\"/>"));
        var top = chart.Title is { Length: > 0 } ? TitleRoom : NoTitleRoom;
        if (chart.Title is { Length: > 0 } title)
        {
            svg.Append(Inv($"<text x=\"{w / 2.0}\" y=\"20\" text-anchor=\"middle\" class=\"xc-chart-title\">{Esc(title)}</text>"));
        }
        var plot = new ChartPlot(Left, top, w - Left - RightPad, h - top - AxisRoom - LegendH);
        var series = chart.Series.Where(s => s.Values.Count > 0).ToList();
        Legend(svg, series, w, h);
        if (chart.Kind == "pie")
        {
            Pie(svg, series, plot);
        }
        else
        {
            var categories = chart.Categories.Count > 0 ? chart.Categories : (series.FirstOrDefault()?.Values ?? []).Select((_, i) => (i + 1).ToString(CultureInfo.InvariantCulture)).ToList();
            Axes(svg, chart, series, categories, plot);
        }
        svg.Append("</svg>");
        return svg.ToString();
    }

    private static void Legend(StringBuilder svg, IReadOnlyList<ChartSeries> series, int w, int h)
    {
        for (var i = 0; i < series.Count; i++)
        {
            var x = 12 + (i * Math.Min(150, (w - 24) / (double)Math.Max(1, series.Count)));
            var name = series[i].Name.Length > 0 ? series[i].Name : $"Series {i + 1}";
            svg.Append(Inv($"<rect x=\"{x}\" y=\"{h - 15}\" width=\"10\" height=\"10\" fill=\"{Colour(i)}\"/>"));
            svg.Append(Inv($"<text x=\"{x + 14}\" y=\"{h - 6}\" class=\"xc-chart-legend\">{Esc(name)}</text>"));
        }
    }

    private static void Pie(StringBuilder svg, IReadOnlyList<ChartSeries> series, ChartPlot plot)
    {
        var values = (series.FirstOrDefault()?.Values ?? []).Select(v => Math.Max(0, v ?? 0)).ToList();
        var sum = values.Sum() is var s && s > 0 ? s : 1;
        var (cx, cy) = (plot.Left + (plot.W / 2.0), plot.Top + (plot.H / 2.0) + 8);
        var r = Math.Max(20, Math.Min(plot.W, plot.H) / 2.0);
        var angle = -Math.PI / 2;
        for (var i = 0; i < values.Count; i++)
        {
            var next = angle + (values[i] / sum * Math.PI * 2);
            var large = next - angle > Math.PI ? 1 : 0;
            var d = Inv($"M{cx},{cy} L{cx + (r * Math.Cos(angle))},{cy + (r * Math.Sin(angle))} A{r},{r} 0 {large} 1 {cx + (r * Math.Cos(next))},{cy + (r * Math.Sin(next))} Z");
            svg.Append(Inv($"<path d=\"{d}\" fill=\"{Colour(i)}\" class=\"xc-chart-slice\"/>"));
            angle = next;
        }
    }

    private static void Axes(StringBuilder svg, PreviewChart chart, IReadOnlyList<ChartSeries> series, IReadOnlyList<string> categories, ChartPlot plot)
    {
        var all = series.SelectMany(s => s.Values).OfType<double>().ToList();
        var max = all.Append(0).Max();
        var min = all.Append(0).Min();
        var span = max - min is var sp && sp != 0 ? sp : 1;
        double Y(double v) => plot.Top + plot.H - ((v - min) / span * plot.H);
        svg.Append(Inv($"<line x1=\"{plot.Left}\" x2=\"{plot.Left + plot.W}\" y1=\"{Y(0)}\" y2=\"{Y(0)}\" class=\"xc-chart-axis\"/>"));
        foreach (var v in new[] { max, (max + min) / 2, min })
        {
            var tick = Math.Abs(v) >= 1000 ? Inv($"{Math.Round(v / 1000)}k") : Inv($"{Math.Round(v * 100) / 100}");
            svg.Append(Inv($"<text x=\"{plot.Left - 6}\" y=\"{Y(v) + 4}\" text-anchor=\"end\" class=\"xc-chart-tick\">{tick}</text>"));
        }
        var bars = series.Where(s => s.Kind != "line" && chart.Kind != "line").ToList();
        var lines = series.Where(s => s.Kind == "line" || chart.Kind == "line").ToList();
        var slot = plot.W / (double)Math.Max(1, categories.Count);
        for (var j = 0; j < categories.Count; j++)
        {
            var c = categories[j].Length > MaxCategory ? categories[j][..(MaxCategory - 1)] + "…" : categories[j];
            svg.Append(Inv($"<text x=\"{plot.Left + (slot * (j + 0.5))}\" y=\"{plot.Top + plot.H + 14}\" text-anchor=\"middle\" class=\"xc-chart-tick\">{Esc(c)}</text>"));
        }
        if (chart.Kind == "bar")
        {
            Horizontal(svg, series, bars, categories.Count, plot, min, span);
            return;
        }
        for (var i = 0; i < bars.Count; i++)
        {
            var width = slot * 0.8 / bars.Count;
            for (var j = 0; j < bars[i].Values.Count; j++)
            {
                if (bars[i].Values[j] is { } v)
                {
                    svg.Append(Inv($"<rect x=\"{plot.Left + (slot * j) + (slot * 0.1) + (width * i)}\" y=\"{Math.Min(Y(0), Y(v))}\" width=\"{width}\" height=\"{Math.Abs(Y(v) - Y(0))}\" fill=\"{Colour(IndexOf(series, bars[i]))}\"/>"));
                }
            }
        }
        foreach (var s in lines)
        {
            var points = string.Join(' ', s.Values.Select((v, j) => v is { } n ? Inv($"{plot.Left + (slot * (j + 0.5))},{Y(n)}") : null).OfType<string>());
            svg.Append(Inv($"<polyline points=\"{points}\" fill=\"none\" stroke=\"{Colour(IndexOf(series, s))}\" stroke-width=\"2.5\"/>"));
        }
    }

    private static void Horizontal(StringBuilder svg, IReadOnlyList<ChartSeries> series, IReadOnlyList<ChartSeries> bars, int count, ChartPlot plot, double min, double span)
    {
        var band = plot.H / (double)Math.Max(1, count);
        double X(double v) => plot.Left + ((v - min) / span * plot.W);
        for (var i = 0; i < bars.Count; i++)
        {
            var height = band * 0.8 / bars.Count;
            for (var j = 0; j < bars[i].Values.Count; j++)
            {
                if (bars[i].Values[j] is { } v)
                {
                    svg.Append(Inv($"<rect x=\"{Math.Min(X(0), X(v))}\" y=\"{plot.Top + (band * j) + (band * 0.1) + (height * i)}\" width=\"{Math.Abs(X(v) - X(0))}\" height=\"{height}\" fill=\"{Colour(IndexOf(series, bars[i]))}\"/>"));
                }
            }
        }
    }

    private static int IndexOf(IReadOnlyList<ChartSeries> series, ChartSeries one) => series.ToList().IndexOf(one);

    private static string Esc(string text) => WebUtility.HtmlEncode(text);

    private static string Inv(FormattableString text) => text.ToString(CultureInfo.InvariantCulture);
}
