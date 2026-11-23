namespace SwissArmyBench.Web.Components;

/// <summary>
/// Where a page's panes are (the owner, 2026-11-23: "both properties and library should be hidable and moveable so
/// the user can choose where they go. they both can even be stack on the right or left over top of each other"):
/// each pane's side, shown or hidden, and its share of its side's height; each side's width. Every change is a new
/// layout (PaneDockState keeps the one in use and remembers it in this browser).
/// </summary>
/// <param name="Spots">Every pane the page has, in order: on one side the earlier is drawn above the later.</param>
/// <param name="LeftWidth">The left side's width in pixels.</param>
/// <param name="RightWidth">The right side's width in pixels.</param>
public sealed record DockLayout(
    IReadOnlyList<DockSpot> Spots,
    double LeftWidth = DockLayout.DefaultWidth,
    double RightWidth = DockLayout.DefaultWidth)
{
    /// <summary>A side's width unless it was changed.</summary>
    public const double DefaultWidth = 280;

    /// <summary>The narrowest and widest a side goes (the classic sidePanes.ts: 200 to 560 px).</summary>
    public const double Narrowest = 200;

    public const double Widest = 560;

    /// <summary>The smallest share of a stacked pair one pane keeps (its header and a few lines stay in view).</summary>
    public const double SmallestShare = 0.15;

    /// <summary>The shown panes on a side, top to bottom.</summary>
    public IReadOnlyList<DockSpot> On(DockSide side) => Spots.Where(s => s.Side == side && s.Shown).ToList();

    public bool IsShown(string id) => Find(id)?.Shown ?? false;

    public DockSide SideOf(string id) => Find(id)?.Side ?? DockSide.Right;

    public double Width(DockSide side) => side == DockSide.Left ? LeftWidth : RightWidth;

    public DockLayout Toggle(string id) => Change(id, s => s with { Shown = !s.Shown });

    public DockLayout Hide(string id) => Change(id, s => s with { Shown = false });

    public DockLayout Show(string id) => Change(id, s => s with { Shown = true });

    /// <summary>The pane moved to a side, shown, at its foot (below the panes already there).</summary>
    public DockLayout MoveTo(string id, DockSide side)
    {
        if (Find(id) is not { } spot)
        {
            return this;
        }
        var moved = spot with { Side = side, Shown = true, Weight = 1 };
        return this with { Spots = [.. Spots.Where(s => s.Id != id), moved] };
    }

    /// <summary>A side's width, kept between the narrowest and the widest.</summary>
    public DockLayout WithWidth(DockSide side, double width)
    {
        var kept = Math.Clamp(width, Narrowest, Widest);
        return side == DockSide.Left ? this with { LeftWidth = kept } : this with { RightWidth = kept };
    }

    /// <summary>The line between the shown pane at <paramref name="upper"/> on a side and the one below it put at
    /// <paramref name="fraction"/> of their two heights (each keeps at least SmallestShare).</summary>
    public DockLayout Split(DockSide side, int upper, double fraction)
    {
        var shown = On(side);
        if (upper < 0 || upper + 1 >= shown.Count)
        {
            return this;
        }
        var (top, bottom) = (shown[upper], shown[upper + 1]);
        var total = top.Weight + bottom.Weight;
        var share = Math.Clamp(fraction, SmallestShare, 1 - SmallestShare);
        return Change(top.Id, s => s with { Weight = total * share }).Change(bottom.Id, s => s with { Weight = total * (1 - share) });
    }

    /// <summary>The upper pane's share of the stacked pair at <paramref name="upper"/> (for the splitter's keys).</summary>
    public double Share(DockSide side, int upper)
    {
        var shown = On(side);
        return upper < 0 || upper + 1 >= shown.Count ? 1 : shown[upper].Weight / (shown[upper].Weight + shown[upper + 1].Weight);
    }

    /// <summary>A layout kept from before, made to fit the page's panes now: a pane the page no longer has left out,
    /// a new pane where its default puts it, the widths kept in range; nothing kept, the defaults.</summary>
    public static DockLayout Recalled(DockLayout? kept, DockLayout defaults)
    {
        if (kept?.Spots is null)
        {
            return defaults;
        }
        var known = defaults.Spots.Select(s => s.Id).ToHashSet();
        var spots = kept.Spots.Where(s => s is not null && known.Contains(s.Id)).DistinctBy(s => s.Id)
            .Select(s => s with { Weight = s.Weight > 0 ? s.Weight : 1 })
            .ToList();
        spots.AddRange(defaults.Spots.Where(d => spots.All(s => s.Id != d.Id)));
        return new DockLayout(spots).WithWidth(DockSide.Left, kept.LeftWidth).WithWidth(DockSide.Right, kept.RightWidth);
    }

    private DockSpot? Find(string id) => Spots.FirstOrDefault(s => s.Id == id);

    private DockLayout Change(string id, Func<DockSpot, DockSpot> change) =>
        this with { Spots = Spots.Select(s => s.Id == id ? change(s) : s).ToList() };
}
