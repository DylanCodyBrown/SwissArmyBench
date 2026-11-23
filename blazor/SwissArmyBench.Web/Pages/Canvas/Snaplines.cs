namespace SwissArmyBench.Web.Pages.Canvas;

/// <summary>
/// The designer's snaplines (the classic canvasSnap.ts; the owner, 2026-11-19: "Snaplines and alignment like
/// WinForms"): while a block is dragged, a guide wherever one of its edges or its centre lines up with another block's,
/// and the block nudged onto the nearest one. Pure maths over rectangles.
/// </summary>
public static class Snaplines
{
    /// <summary>The guides of <paramref name="moving"/> against the others: one line for each of its lines that
    /// matches another block's line of the same sort (an edge an edge, a centre a centre).</summary>
    public static IReadOnlyList<Guide> Guides(BoardRect moving, IReadOnlyList<BoardRect> others, double tolerance = 1)
    {
        var axes = new[] { "v", "h" };
        return axes
            .SelectMany(axis => Lines(moving, axis).Select(line => (axis, line)))
            .Select(found =>
            {
                var matched = others
                    .Where(o => o.Id != moving.Id && Lines(o, found.axis).Any(l => Math.Abs(l.At - found.line.At) <= tolerance && IsCentre(l.Edge) == IsCentre(found.line.Edge)))
                    .ToList();
                if (matched.Count == 0)
                {
                    return null;
                }
                var all = matched.Prepend(moving).ToList();
                var from = all.Min(r => found.axis == "v" ? r.Top : r.Left);
                var to = all.Max(r => found.axis == "v" ? r.Bottom : r.Right);
                return new Guide(found.axis, found.line.At, from, to, found.line.Edge, matched.Select(m => m.Id).ToList());
            })
            .OfType<Guide>()
            .ToList();
    }

    /// <summary><paramref name="moving"/> moved onto the nearest line of another block, per axis, when one is within
    /// the tolerance.</summary>
    public static BoardRect Nudged(BoardRect moving, IReadOnlyList<BoardRect> others, double tolerance = 6) =>
        moving with { Left = moving.Left + Shift(moving, others, "v", tolerance), Top = moving.Top + Shift(moving, others, "h", tolerance) };

    private static double Shift(BoardRect moving, IReadOnlyList<BoardRect> others, string axis, double tolerance)
    {
        var best = Lines(moving, axis)
            .SelectMany(mine => others
                .Where(o => o.Id != moving.Id)
                .SelectMany(o => Lines(o, axis))
                .Where(theirs => IsCentre(theirs.Edge) == IsCentre(mine.Edge))
                .Select(theirs => theirs.At - mine.At))
            .OrderBy(Math.Abs)
            .Select(gap => (double?)gap)
            .FirstOrDefault();
        return best is { } shift && Math.Abs(shift) <= tolerance ? shift : 0;
    }

    private static bool IsCentre(string edge) => edge is "centre" or "middle";

    private static IEnumerable<(string Edge, double At)> Lines(BoardRect r, string axis) => axis == "v"
        ? [("left", r.Left), ("centre", r.Left + (r.Width / 2)), ("right", r.Right)]
        : [("top", r.Top), ("middle", r.Top + (r.Height / 2)), ("bottom", r.Bottom)];
}
