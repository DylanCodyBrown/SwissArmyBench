using SwissArmyBench.Web.Components;

namespace SwissArmyBench.Web.Pages.Workbench;

/// <summary>A tab's right click (the Notebooks and Scripts pages): its splits, Rename… (F2; the owner, 2026-11-24: "we
/// should allow renaming here"), and Close. Rename… is a notebook's, a script's and a SQL file's; a blade, a structure,
/// a workbook and a code app's file are renamed their own ways.</summary>
public static class TabMenus
{
    public const string RenameElsewhere = "Renamed in its own screen";

    public static IReadOnlyList<MenuEntry> Entries(OpenDocument doc, MenuEntry splitRight, MenuEntry splitDown, Func<Task> rename, Func<Task> close) =>
    [
        splitRight,
        splitDown,
        MenuEntry.Separator,
        new("Rename…", "edit", rename, doc.CanRename ? null : RenameElsewhere, "F2"),
        new("Close", "close", close),
    ];
}
