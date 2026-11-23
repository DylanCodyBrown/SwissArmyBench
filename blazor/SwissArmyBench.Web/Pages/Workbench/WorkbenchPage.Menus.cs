using Microsoft.AspNetCore.Components;
using Microsoft.AspNetCore.Components.Web;

using SwissArmyBench.Web.Api;
using SwissArmyBench.Web.Api.Projects;
using SwissArmyBench.Web.Api.Settings;
using SwissArmyBench.Web.Components;
using SwissArmyBench.Web.Pages.Workbench.Tabs;

namespace SwissArmyBench.Web.Pages.Workbench;

// The page's menus (the classic workbenchBars.ts and workbenchPage.ts): the top bar's "…" and the project's, a group's
// "+" New tab and a tab's right click, "+ Cell", and a document's "…"; and the project's actions they run.
public partial class WorkbenchPage
{
    private ExplorerAnswer? _newProject;
    private bool _betaOn;
    private MouseEventArgs _lastClick = new();

    private bool CanSplit(OpenDocument? doc) => doc is not null && _layout.CanSplit(doc.Key);

    private MenuEntry SplitEntry(OpenDocument? doc, SplitSide side, string? keys = null) =>
        new(side == SplitSide.Right ? "Split right" : "Split down", side == SplitSide.Right ? "splitRight" : "splitDown",
            () => SplitAsync(doc, side), CanSplit(doc) ? null : SplitWhy, keys);

    /// <summary>The top bar's "…": what makes a document, opens one, splits the groups, and every command.</summary>
    private (string, IReadOnlyList<MenuEntry>) TopMenu() => ("Workbench menu",
    [
        .. NewEntries(),
        MenuEntry.Separator,
        SplitEntry(Front, SplitSide.Right, "Ctrl+\\"),
        SplitEntry(Front, SplitSide.Down),
        MenuEntry.Separator,
        new("Layout: source only", "max", () => LayoutAsync(false), Keys: "Ctrl+Shift+1"),
        new("Layout: standard", "restore", () => LayoutAsync(true)),
        new(_showExplorer ? "Close the Data Explorer" : "Data Explorer", "data", ToggleExplorerAsync, Keys: "Ctrl+Shift+E"),
        MenuEntry.Separator,
        new("Commands…", "steps", () => Toggle(() => _palette = true), Keys: "Ctrl+Shift+P"),
        new("Settings…", "cog", () => Go("settings")),
        MenuEntry.Separator,
        _betaOn ? new("Turn beta mode off", "exclude", () => GuardAsync(() => SetBetaAsync(false))) : new("Turn beta mode on", "check", () => GuardAsync(() => SetBetaAsync(true))),
        new("Export beta log…", "export", () => GuardAsync(ExportBetaLogAsync)),
    ]);

    private async Task SetBetaAsync(bool on) => _betaOn = (await SettingsApi.SetBetaAsync(on)).On;

    private async Task ExportBetaLogAsync()
    {
        if (await Files.ChooseAsync("save", "Export beta log", null, "file", "beta-log.zip") is { } path)
        {
            await SettingsApi.ExportBetaLogAsync(path);
            await Notes.SayAsync($"Saved to {path}");
        }
    }

    /// <summary>In this project…: the documents of the page's kind opened lately, each opened on its click.</summary>
    private async Task InThisProjectAsync(MouseEventArgs at)
    {
        var extension = IsNotebooks ? ".ipynb" : ".py";
        _recent = await RecentAsync();
        List<MenuEntry> entries = _recent
            .Where(r => r.Exists && r.Path.EndsWith(extension, StringComparison.OrdinalIgnoreCase))
            .Select(r => new MenuEntry(System.IO.Path.GetFileName(r.Path), IsNotebooks ? "notebook" : "code", async () =>
            {
                await OpenPathAsync(r.Path);
                await FollowAddressAsync();
            }))
            .ToList();
        await ShowMenuAsync(at, ("In this project", entries.Count > 0 ? entries : [new("Nothing opened lately", "more", () => Task.CompletedTask, "Nothing opened lately")]));
    }

    /// <summary>What a group's "+" and the top bar's "…" make: the page's kind, the project's entries, Open.</summary>
    private List<MenuEntry> NewEntries() =>
    [
        new($"New {KindWord}", IsNotebooks ? "notebook" : "code", NewAsync),
        .. CanvasEntries(),
        .. LanguageEntries(),
        MenuEntry.Separator,
        .. ProjectEntries(),
        MenuEntry.Separator,
        new("Open…", "folder", OpenAsync, Keys: "Ctrl+O"),
        new("In this project…", "more", () => InThisProjectAsync(_lastClick)),
        new("Import…", "import", () => Toggle(() => _importKind = "documents"), Project.Current is null ? NoProject : null),
    ];

    private (string, IReadOnlyList<MenuEntry>) NewTabMenu() => ("New tab", NewEntries());

    private (string, IReadOnlyList<MenuEntry>) ProjectMenu() => ("Project", ProjectEntries());

    /// <summary>A tab's right click: its moves, and Close.</summary>
    private (string, IReadOnlyList<MenuEntry>) TabMenu(int key)
    {
        var doc = _byKey[key];
        return ("Tab menu",
        [
            SplitEntry(doc, SplitSide.Right),
            SplitEntry(doc, SplitSide.Down),
            MenuEntry.Separator,
            new("Close", "close", () => CloseAsync(key)),
        ]);
    }

    /// <summary>The project's entries: New project…, Open project…, Export data.py, and with one open, Copy project
    /// to…, Export outline and Close project.</summary>
    private List<MenuEntry> ProjectEntries()
    {
        var open = Project.Current is not null;
        List<MenuEntry> entries =
        [
            new("New project…", "plus", NewProjectAsync),
            new("Open project…", "folder", () => GuardAsync(OpenProjectAsync)),
            new("Export data.py", "export", () => GuardAsync(ExportDataAsync), open ? null : "No project is open"),
        ];
        if (open)
        {
            entries.AddRange(
            [
                MenuEntry.Separator,
                new("Copy project to…", "copy", () => GuardAsync(CopyProjectAsync)),
                new("Export outline", "outline", () => GuardAsync(ExportOutlineAsync)),
                new("Close project", "close", () => GuardAsync(CloseProjectAsync)),
            ]);
        }
        return entries;
    }

    /// <summary>"+ Cell": the kinds a notebook's cell can be.</summary>
    private (string, IReadOnlyList<MenuEntry>) CellMenu(OpenDocument doc)
    {
        var view = doc.NotebookView;
        Func<Task> add(string kind) => () => view?.AddCellAsync(kind) ?? Task.CompletedTask;
        return ("Cell kinds",
        [
            new("Python", "code", add("code"), Keys: "B"),
            new("SQL", "sql", add("sql")),
            new("DAX", "group", add("dax")),
            new("HTML", "image", add("html")),
            new("Markdown", "edit", add("markdown")),
            .. ModeCellEntries(),
        ]);
    }

    private static readonly string[] _baseCellKinds = ["code", "python", "sql", "dax", "html", "markdown"];

    private static readonly Dictionary<string, string> _languageWords = new() { ["typescript"] = "TypeScript", ["tsx"] = "TSX", ["javascript"] = "JavaScript" };

    /// <summary>The open project's mode's own cell kinds (a code app's TypeScript and TSX): run in the classic data
    /// notebook's kernel, so offered here as coming.</summary>
    private IEnumerable<MenuEntry> ModeCellEntries() => _cellKinds
        .Where(k => !_baseCellKinds.Contains(k))
        .Select(k => new MenuEntry($"{_languageWords.GetValueOrDefault(k, k)} (coming)", "code", () => Task.CompletedTask, "Coming: a later version runs these cells"));

    /// <summary>A group's "…": the rest of what the document in front does.</summary>
    private (string, IReadOnlyList<MenuEntry>) DocumentMenu(OpenDocument doc)
    {
        List<MenuEntry> entries = doc.IsNotebook
            ? [new("Clear every output", "clean", () => Toggle(() => doc.NotebookView?.ClearAll()))]
            : [new("Run statement", "play", () => doc.ScriptView?.RunSelectionAsync() ?? Task.CompletedTask, Keys: "Ctrl+Enter")];
        entries.AddRange(
        [
            MenuEntry.Separator,
            new("Open…", "folder", OpenAsync, Keys: "Ctrl+O"),
            new("In this project…", "more", () => InThisProjectAsync(_lastClick)),
            new("Import…", "import", () => Toggle(() => _importKind = "documents"), Project.Current is null ? NoProject : null),
            new("Save", "save", () => SaveAsync(doc), Keys: "Ctrl+S"),
            new("Save as…", "save", () => SaveAsAsync(doc), Keys: "Ctrl+Shift+S"),
            new("Export as one Python script…", "export", () => GuardAsync(() => ExportDocumentAsync(doc, "script"))),
            new("Export as one notebook…", "export", () => GuardAsync(() => ExportDocumentAsync(doc, "notebook"))),
            MenuEntry.Separator,
            .. SessionEntries(),
            MenuEntry.Separator,
            SplitEntry(doc, SplitSide.Right, "Ctrl+\\"),
            SplitEntry(doc, SplitSide.Down),
            new("Open in its own window", "popout", () => PopOutAsync(doc), doc.Path is null ? "Save it first: its own window opens its file" : null),
            _popped ? new("Move to the main window", "back", () => MoveToMainAsync(doc)) : MenuEntry.Separator,
            new("Close", "close", () => CloseAsync(doc.Key)),
        ]);
        return ("Document menu", entries);
    }

    /// <summary>The session's entries: for a project's document they say whose they are, with its Libraries….</summary>
    private List<MenuEntry> SessionEntries() => Session.Shared is null
        ? [new("Interrupt", "stop", InterruptAsync), new("Restart", "back", RestartAsync)]
        :
        [
            new("Interrupt the project's Python session", "stop", InterruptAsync),
            new("Restart the project's Python session", "back", RestartAsync),
            new("Libraries…", "settings", () => Go("environment?at=libraries")),
        ];

    [Inject]
    private SettingsClient SettingsApi { get; set; } = default!;

    private Task Go(string address)
    {
        Nav.NavigateTo(address);
        return Task.CompletedTask;
    }

    private async Task NewProjectAsync()
    {
        try
        {
            _newProject = await ProjectsApi.ExplorerAsync(string.Empty, string.Empty, string.Empty);
        }
        catch (ApiException error)
        {
            _error = error;
        }
    }

    private async Task NewProjectDoneAsync(bool made)
    {
        _newProject = null;
        if (made)
        {
            await Project.RefreshAsync();
            await LoadTreeAsync();
        }
    }

    private async Task OpenProjectAsync()
    {
        var listing = await ProjectsApi.ExplorerAsync(string.Empty, string.Empty, string.Empty);
        if (await Files.ChooseAsync("folder", "Open project", listing.Folder, "project") is not { } path)
        {
            return;
        }
        try
        {
            await ProjectsApi.OpenAsync(path);
        }
        catch (ApiException error) when (error.Status == ConflictStatus)
        {
            if (!await Dialogs.AskYesNoAsync("Open project", error.Refusal.Error, "Discard and open", danger: true))
            {
                return;
            }
            await ProjectsApi.OpenAsync(path, discard: true);
        }
        await Project.RefreshAsync();
        await LoadTreeAsync();
    }

    private async Task CloseProjectAsync()
    {
        try
        {
            await ProjectsApi.CloseAsync();
        }
        catch (ApiException error) when (error.Status == ConflictStatus)
        {
            if (!await Dialogs.AskYesNoAsync("Close project", error.Refusal.Error, "Close without saving", danger: true))
            {
                return;
            }
            await ProjectsApi.CloseAsync(discard: true);
        }
        await Project.RefreshAsync();
        await LoadTreeAsync();
    }
}
