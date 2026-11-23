using Microsoft.AspNetCore.Components;
using Microsoft.AspNetCore.Components.Web;

using SwissArmyBench.Web.Api.Workbench;
using SwissArmyBench.Web.Components;

namespace SwissArmyBench.Web.Pages.Workbench;

public partial class FilesPane
{
    /// <summary>The file actions the page carries out (FileActionsDialog): rename, duplicate, delete, and a package's.</summary>
    public const string Rename = "rename";
    public const string Duplicate = "duplicate";
    public const string Delete = "delete";
    public const string RenamePackage = "rename-package";
    public const string NewPackageHere = "new-package";
    public const string DeletePackage = "delete-package";

    private readonly HashSet<string> _unfolded = [];
    private string _find = string.Empty;
    private ShownMenu? _menu;

    [Parameter, EditorRequired]
    public string Page { get; set; } = "scripts";

    [Parameter]
    public CodeTree? Tree { get; set; }

    /// <summary>The document in front (marked in the list).</summary>
    [Parameter]
    public string? Current { get; set; }

    [Parameter]
    public EventCallback OnRefresh { get; set; }

    [Parameter]
    public EventCallback OnNew { get; set; }

    /// <summary>A symbol's line: its file opened there.</summary>
    [Parameter]
    public EventCallback<(string Path, int Line)> OnOpenAt { get; set; }

    /// <summary>A file action (its file, or null for a new package in scripts/), for the page.</summary>
    [Parameter]
    public EventCallback<(TreeFile? File, string Action)> OnAction { get; set; }

    private (string Title, string One) Words => Page == "scripts" ? ("Scripts", "script") : ("Notebooks", "notebook");

    /// <summary>The groups with the files Find matches (a path, a module, or a symbol of its outline).</summary>
    private List<(TreeGroup Group, List<TreeFile> Files)> Shown
    {
        get
        {
            var q = _find.Trim();
            return (Tree?.Groups ?? [])
                .Select(g => (Group: g, Files: q.Length == 0 ? g.Files.ToList() : g.Files.Where(f => Matches(f.Path) || Matches(f.Module ?? string.Empty) || (f.Outline ?? []).Any(SymbolMatches)).ToList()))
                .Where(g => g.Files.Count > 0)
                .ToList();
        }
    }

    private bool Matches(string text) => text.Contains(_find.Trim(), StringComparison.OrdinalIgnoreCase);

    private bool SymbolMatches(TreeSymbol s) => Matches(s.Name) || s.Children.Any(SymbolMatches);

    private static IEnumerable<(TreeSymbol Symbol, int Depth)> Flat(IEnumerable<TreeSymbol> symbols, int depth) =>
        symbols.SelectMany(s => Flat(s.Children, depth + 1).Prepend((s, depth)));

    private void Fold(string full)
    {
        if (!_unfolded.Remove(full))
        {
            _unfolded.Add(full);
        }
    }

    private bool Same(string path) => string.Equals(path, Current, StringComparison.Ordinal);

    /// <summary>A module of the user's own: it has the right click's actions (never a made, library or other file).</summary>
    private bool Own(TreeFile file) => Page == "scripts" && !file.ReadOnly && file.MadeFrom is null && !file.Library && file.Path.EndsWith(".py", StringComparison.Ordinal);

    /// <summary>A file opens on its kind's page (a notebook on Notebooks, a .py on Scripts).</summary>
    private static string AddressOf(string path) =>
        $"{(path.EndsWith(".ipynb", StringComparison.OrdinalIgnoreCase) ? "notebooks" : "scripts")}?path={Uri.EscapeDataString(path)}";

    private Task MenuAsync(MouseEventArgs at, TreeFile file)
    {
        if (!Own(file))
        {
            return Task.CompletedTask;
        }
        Func<Task> act(string action) => () => OnAction.InvokeAsync((file, action));
        List<MenuEntry> entries =
        [
            new("Rename…", "edit", act(Rename)),
            new("Duplicate", "copy", act(Duplicate)),
            new("Delete", "trash", act(Delete)),
        ];
        if (file.Name == "__init__.py")
        {
            entries.AddRange([MenuEntry.Separator, new("Rename package…", "edit", act(RenamePackage)), new("New package here…", "folder", act(NewPackageHere)), new("Delete package", "trash", act(DeletePackage))]);
        }
        _menu = new ShownMenu($"{file.Name} actions", entries, at.ClientX, at.ClientY);
        return Task.CompletedTask;
    }

    private Task KeyAsync(KeyboardEventArgs e, TreeFile file) => !Own(file)
        ? Task.CompletedTask
        : e.Key switch
        {
            "F2" => OnAction.InvokeAsync((file, Rename)),
            "Delete" => OnAction.InvokeAsync((file, Delete)),
            _ => Task.CompletedTask,
        };
}
