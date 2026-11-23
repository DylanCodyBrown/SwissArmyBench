using SwissArmyBench.Web.Components;

namespace SwissArmyBench.Web.Pages.Accounting;

/// <summary>A menu of the Excel canvas open under its button: Blocks, or Templates and statements.</summary>
public sealed record WorkbookMenu(string Title, double X, double Y, IReadOnlyList<MenuEntry> Entries);
