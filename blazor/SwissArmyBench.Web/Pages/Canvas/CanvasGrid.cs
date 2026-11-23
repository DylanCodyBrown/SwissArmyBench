namespace SwissArmyBench.Web.Pages.Canvas;

/// <summary>
/// The Canvas's placement maths (the classic canvasGrid.ts; the owner, 2026-11-21: "should be able to turn on snap
/// to", "with a very fine precision"). Pure: rectangles in the page's pixels.
/// </summary>
public static class CanvasGrid
{
    // The dots stay readable: never closer than this many screen pixels.
    private const double FewestDotPixels = 12;

    // The grid's dots when the step is the grid's cells.
    private const int GridDots = 8;

    /// <summary>The column lines of a box: each column's left and right edge.</summary>
    public static IReadOnlyList<double> Lines(double width, int columns, double gap)
    {
        var column = Math.Max(1, (width - ((columns - 1) * gap)) / columns);
        return Enumerable.Range(0, columns)
            .SelectMany(i => new[] { i * (column + gap), (i * (column + gap)) + column })
            .ToList();
    }

    /// <summary>The rectangle on the step (or the grid's cells), then onto another item's edge or centre within the
    /// tolerance (moving only: a size keeps its corner); snap off: whole pixels only.</summary>
    public static Snapped Snap(BoardRect rect, SnapSettings snap)
    {
        if (!snap.On)
        {
            return new Snapped(Whole(rect, rect.Left, rect.Top, rect.Width, rect.Height), []);
        }
        var (left, top, width, height) = (rect.Left, rect.Top, rect.Width, rect.Height);
        if (snap.Step.Grid)
        {
            var columns = Lines(snap.Grid.Width, snap.Grid.Columns, snap.Grid.Gap);
            var rows = RowLines(snap.Grid, top + height);
            if (snap.Sizing)
            {
                width = Nearest(left + width, columns) - left;
                height = Nearest(top + height, rows) - top;
            }
            else
            {
                left = Nearest(left, columns);
                top = Nearest(top, rows);
            }
        }
        else
        {
            double On(double v) => Round(v / snap.Step.Pixels) * snap.Step.Pixels;
            if (snap.Sizing)
            {
                width = On(left + width) - left;
                height = On(top + height) - top;
            }
            else
            {
                left = On(left);
                top = On(top);
            }
        }
        var made = Whole(rect, left, top, width, height);
        if (!snap.Sizing && snap.Others.Count > 0)
        {
            var near = Snaplines.Nudged(made, snap.Others, snap.Tolerance);
            made = made with { Left = Round(near.Left), Top = Round(near.Top) };
        }
        return new Snapped(made, Snaplines.Guides(made, snap.Others, 0.5));
    }

    /// <summary>How far an arrow key moves the selection: one pixel with Alt, ten steps with Shift, else one step (a
    /// grid cell and its gap when the step is the grid's).</summary>
    public static double NudgeBy(SnapStep step, bool shift, bool alt, GridSpec grid)
    {
        if (alt)
        {
            return 1;
        }
        var one = step.Grid ? Round(Math.Max(1, (grid.Width - ((grid.Columns - 1) * grid.Gap)) / grid.Columns) + grid.Gap) : step.Pixels;
        return shift ? one * 10 : one;
    }

    /// <summary>The dots' spacing in page pixels: the step, doubled until they are 12 screen pixels apart.</summary>
    public static double DotSpacing(SnapStep step, double zoom)
    {
        double spacing = step.Grid ? GridDots : step.Pixels;
        while (spacing * zoom < FewestDotPixels)
        {
            spacing *= 2;
        }
        return spacing;
    }

    private static BoardRect Whole(BoardRect rect, double left, double top, double width, double height) =>
        rect with { Left = Round(left), Top = Round(top), Width = Math.Max(1, Round(width)), Height = Math.Max(1, Round(height)) };

    /// <summary>Rounded as the classic page rounds (half up, the browser's Math.round).</summary>
    public static double Round(double value) => Math.Floor(value + 0.5);

    private static double Nearest(double value, IReadOnlyList<double> lines) =>
        lines.Count == 0 ? value : lines.MinBy(line => Math.Abs(line - value));

    private static List<double> RowLines(GridSpec grid, double upTo)
    {
        var step = grid.RowHeight + grid.Gap;
        var count = (int)Math.Floor((upTo + (grid.RowHeight * 2)) / step) + 1;
        return Enumerable.Range(0, Math.Max(0, count))
            .SelectMany(i => new[] { i * step, (i * step) + grid.RowHeight })
            .Prepend(0)
            .ToList();
    }
}
