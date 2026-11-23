using SwissArmyBench.Web.Components;

namespace SwissArmyBench.Web.Pages.Workbench;

/// <summary>A menu open on the page: its heading, its lines, and where (under the button that opened it, or at the
/// pointer for a right click).</summary>
public sealed record ShownMenu(string Title, IReadOnlyList<MenuEntry> Entries, double X, double Y);
