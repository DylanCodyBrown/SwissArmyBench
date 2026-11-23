// Ported from Code - OSS (github.com/microsoft/vscode), src/vs/workbench/contrib/scm/browser/scmHistory.ts.
// Copyright (c) Microsoft Corporation. Licensed under the MIT License (THIRD_PARTY_NOTICES.md has its text).
using System.Globalization;

namespace SwissArmyBench.Web.Pages.Scm;

/// <summary>
/// The Source Control page's graph (the classic scmGraph.ts; the owner, 2026-11-18: "literally clone to exactly no
/// deviation"): VS Code's swimlanes, the same sizes, curves, circles and the five lane colours (--vscode-* ids).
/// ViewModels gives each commit's input and output swimlanes; Shapes one row's lines and circle.
/// </summary>
public static class ScmGraph
{
    public const double SwimlaneHeight = 22;
    public const double SwimlaneWidth = 11;
    public const string RefColor = "scmGraph-historyItemRefColor";
    public const string RemoteRefColor = "scmGraph-historyItemRemoteRefColor";
    public const string IncomingId = "scm-graph-incoming-changes";

    private const double CurveRadius = 5;
    private const double CircleRadius = 4;
    private const double CircleStroke = 2;

    private static readonly string[] _colors = ["scmGraph-foreground1", "scmGraph-foreground2", "scmGraph-foreground3", "scmGraph-foreground4", "scmGraph-foreground5"];

    /// <summary>toISCMHistoryItemViewModelArray: each item's swimlanes, in order.</summary>
    public static IReadOnlyList<GraphRow> ViewModels(IReadOnlyList<GraphItem> items, IReadOnlyDictionary<string, string?> colors, string? head)
    {
        var colorIndex = -1;
        var rows = new List<GraphRow>();
        foreach (var item in items)
        {
            var kind = item.Id == IncomingId ? "incoming-changes" : item.Id == head ? "HEAD" : "node";
            var input = rows.Count > 0 ? rows[^1].Output.ToList() : [];
            var output = new List<GraphNode>();
            var firstParentAdded = false;
            if (item.ParentIds.Count > 0)
            {
                foreach (var node in input)
                {
                    if (node.Id == item.Id)
                    {
                        if (!firstParentAdded)
                        {
                            output.Add(new GraphNode(item.ParentIds[0], LabelColor(item, colors) ?? node.Color));
                            firstParentAdded = true;
                        }
                        continue;
                    }
                    output.Add(node);
                }
            }
            for (var i = firstParentAdded ? 1 : 0; i < item.ParentIds.Count; i++)
            {
                var color = i == 0 ? LabelColor(item, colors) : items.FirstOrDefault(h => h.Id == item.ParentIds[i]) is { } parent ? LabelColor(parent, colors) : null;
                if (color is null)
                {
                    colorIndex = (colorIndex + 1) % _colors.Length;
                    color = _colors[colorIndex];
                }
                output.Add(new GraphNode(item.ParentIds[i], color));
            }
            var references = item.References.Select(r => r with { Color = RefColorOf(r, item, colors, input, output) }).ToList();
            rows.Add(new GraphRow(item with { References = references }, kind, input, output));
        }
        return rows;
    }

    /// <summary>renderSCMHistoryItemGraph: one row's lanes and its circle (HEAD a ring, a merge two, Incoming
    /// Changes dashed).</summary>
    public static IReadOnlyList<GraphShape> Shapes(GraphRow row)
    {
        var (item, input, output) = (row.Item, row.Input, row.Output);
        var inputIndex = input.ToList().FindIndex(n => n.Id == item.Id);
        var circleIndex = inputIndex != -1 ? inputIndex : input.Count;
        var circleColor = circleIndex < output.Count ? output[circleIndex].Color : circleIndex < input.Count ? input[circleIndex].Color : RefColor;
        var shapes = new List<GraphShape>();
        shapes.AddRange(Lanes(item, input, output, circleIndex));
        shapes.AddRange(Merges(item, output, circleIndex));
        if (inputIndex != -1)
        {
            shapes.Add(Line(Vertical(X(circleIndex), 0, SwimlaneHeight / 2), input[inputIndex].Color));
        }
        if (item.ParentIds.Count > 0)
        {
            shapes.Add(Line(Vertical(X(circleIndex), SwimlaneHeight / 2, SwimlaneHeight), circleColor));
        }
        shapes.AddRange(Circles(row.Kind, item.ParentIds.Count, circleIndex, circleColor));
        return shapes;
    }

    /// <summary>The graph's width for a row (its lanes and one more).</summary>
    public static double Width(GraphRow row) => SwimlaneWidth * (Math.Max(Math.Max(row.Input.Count, row.Output.Count), 1) + 1);

    private static IEnumerable<GraphShape> Lanes(GraphItem item, IReadOnlyList<GraphNode> input, IReadOnlyList<GraphNode> output, int circleIndex)
    {
        var outputIndex = 0;
        for (var index = 0; index < input.Count; index++)
        {
            var color = input[index].Color;
            if (input[index].Id == item.Id)
            {
                if (index != circleIndex)
                {
                    yield return Line($"M {N(X(index))} 0 A {N(SwimlaneWidth)} {N(SwimlaneWidth)} 0 0 1 {N(SwimlaneWidth * index)} {N(SwimlaneWidth)} H {N(X(circleIndex))}", color);
                }
                else
                {
                    outputIndex++;
                }
            }
            else if (outputIndex < output.Count && input[index].Id == output[outputIndex].Id)
            {
                yield return index == outputIndex
                    ? Line(Vertical(X(index), 0, SwimlaneHeight), color)
                    : Line(
                        $"M {N(X(index))} 0 V 6 A {N(CurveRadius)} {N(CurveRadius)} 0 0 1 {N(X(index) - CurveRadius)} {N(SwimlaneHeight / 2)} "
                        + $"H {N(X(outputIndex) + CurveRadius)} A {N(CurveRadius)} {N(CurveRadius)} 0 0 0 {N(X(outputIndex))} {N((SwimlaneHeight / 2) + CurveRadius)} V {N(SwimlaneHeight)}",
                        color);
                outputIndex++;
            }
        }
    }

    private static IEnumerable<GraphShape> Merges(GraphItem item, IReadOnlyList<GraphNode> output, int circleIndex) => item.ParentIds
        .Skip(1)
        .Select(parent => output.Select(n => n.Id).ToList().LastIndexOf(parent))
        .Where(at => at != -1)
        .Select(at => Line(
            $"M {N(SwimlaneWidth * at)} {N(SwimlaneHeight / 2)} A {N(SwimlaneWidth)} {N(SwimlaneWidth)} 0 0 1 {N(X(at))} {N(SwimlaneHeight)} "
            + $"M {N(SwimlaneWidth * at)} {N(SwimlaneHeight / 2)} H {N(X(circleIndex))} ",
            output[at].Color));

    private static IEnumerable<GraphShape> Circles(string kind, int parents, int at, string color) => kind switch
    {
        "HEAD" => [Circle(at, CircleRadius + 3, CircleStroke, color), Circle(at, CircleStroke, CircleRadius, null)],
        "incoming-changes" =>
        [
            Circle(at, CircleRadius + 3, CircleStroke, color),
            Circle(at, CircleRadius + 1, CircleStroke + 1, null),
            new GraphShape(null, X(at), SwimlaneWidth, CircleRadius + 1, CircleStroke - 1, color, null, Dashed: true),
        ],
        _ when parents > 1 => [Circle(at, CircleRadius + 2, CircleStroke, color), Circle(at, CircleRadius - 1, CircleStroke, color)],
        _ => [Circle(at, CircleRadius + 1, CircleStroke, color)],
    };

    private static string? LabelColor(GraphItem item, IReadOnlyDictionary<string, string?> colors) =>
        item.Id == IncomingId
            ? RemoteRefColor
            : item.References.Where(r => colors.ContainsKey(r.Id)).Select(r => colors[r.Id]).FirstOrDefault(c => c is not null);

    private static string? RefColorOf(GraphRef r, GraphItem item, IReadOnlyDictionary<string, string?> colors, IReadOnlyList<GraphNode> input, IReadOnlyList<GraphNode> output)
    {
        if (!colors.TryGetValue(r.Id, out var color) || color is not null)
        {
            return color;
        }
        var at = input.ToList().FindIndex(n => n.Id == item.Id);
        var circle = at != -1 ? at : input.Count;
        return circle < output.Count ? output[circle].Color : circle < input.Count ? input[circle].Color : RefColor;
    }

    private static double X(int lane) => SwimlaneWidth * (lane + 1);

    private static string Vertical(double x, double y1, double y2) => $"M {N(x)} {N(y1)} V {N(y2)}";

    private static GraphShape Line(string d, string color) => new(d, 0, 0, 0, 1, color, null);

    private static GraphShape Circle(int at, double radius, double width, string? color) => new(null, X(at), SwimlaneWidth, radius, width, null, color);

    private static string N(double value) => value.ToString("0.###", CultureInfo.InvariantCulture);
}
