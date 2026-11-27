using SwissArmyBench.Web.Api.Workbench;
using SwissArmyBench.Web.Components;

namespace SwissArmyBench.Web.Pages.Workbench.Ide;

/// <summary>The New file dropdown's lines (the top bar's button and each group's "+"): one a file type the server
/// names, in its order. With no project open only the types that start as an untitled tab can be picked: the others
/// say why.</summary>
public static class NewFileMenus
{
    public const string NeedsProject = "Open a project first: a new file goes in its folder";

    /// <summary>With no project open these still start, as an untitled tab (a notebook on its own page).</summary>
    public static bool StartsUntitled(NewFileType type) => type.Kind is "script" or "sql" or "notebook";

    public static IReadOnlyList<MenuEntry> Entries(IEnumerable<NewFileType> types, bool project, Func<NewFileType, Task> pick) =>
        [.. types.Select(type => new MenuEntry(type.Line, type.Icon, () => pick(type), project || StartsUntitled(type) ? null : NeedsProject))];
}
