using SwissArmyBench.Web.Api.Workbench;
using SwissArmyBench.Web.Components;

namespace SwissArmyBench.Web.Pages.Workbench.Ide;

/// <summary>The New file list's lines (the top bar's button, the tab strip's "+", the File menu): one a file type the
/// server names, in its order. The server lists only what can be made now (the open project's type's own types;
/// with no project open the ones made in any folder), so every line can be picked.</summary>
public static class NewFileMenus
{
    public static IReadOnlyList<MenuEntry> Entries(IEnumerable<NewFileType> types, Func<NewFileType, Task> pick) =>
        [.. types.Select(type => new MenuEntry(type.Line, type.Icon, () => pick(type)))];
}
