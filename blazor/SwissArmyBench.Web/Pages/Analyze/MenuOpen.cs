using SwissArmyBench.Web.Components;

namespace SwissArmyBench.Web.Pages.Analyze;

/// <summary>A menu open on the Analyze page, at a place.</summary>
public sealed record MenuOpen(IReadOnlyList<MenuEntry> Entries, double X, double Y);
