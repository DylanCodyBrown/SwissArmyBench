namespace SwissArmyBench.Web.Components;

/// <summary>Where one pane is: its side, whether it is shown, and its share of its side's height when it is stacked
/// with another (its weight beside theirs).</summary>
/// <param name="Id">The pane's name ("properties", "library").</param>
/// <param name="Side">The side it is docked on.</param>
/// <param name="Shown">Shown, or hidden until its toggle brings it back.</param>
/// <param name="Weight">Its share of the side's height, against the other shown panes on that side.</param>
public sealed record DockSpot(string Id, DockSide Side, bool Shown = true, double Weight = 1);
