using SwissArmyBench.Web.Components;

namespace SwissArmyBench.Web.Pages.Grids;

/// <summary>The right-click menu on screen: its heading (the cell or the column), its lines, where it opened.</summary>
public sealed record OpenMenu(string Title, IReadOnlyList<MenuEntry> Entries, double X, double Y);
