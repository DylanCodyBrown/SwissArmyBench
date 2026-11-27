using Microsoft.JSInterop;

using SwissArmyBench.Web.Pages.Workbench.Tabs;
using SwissArmyBench.Web.State;

namespace SwissArmyBench.Web.Pages.Workbench;

// The command palette's commands (the classic workbenchCommandList.ts): every action of the page by one name, in
// groups (File, Project, Run, Cell, Documents, Groups, View, Go, Help), each greyed out with its reason when it
// cannot run now.
public partial class WorkbenchPage
{
    private const string NoDocument = "Open a notebook or a script first";
    private const string NoNotebook = "A notebook's command: put a notebook in front";
    private const string NoCell = "Select a cell first";
    private const string NoProject = "No project is open";

    private List<PaletteCommand> Commands() =>
    [
        .. FileCommands(),
        .. ProjectCommands(),
        .. RunCommands(),
        .. CellCommands(),
        .. DocumentCommands(),
        .. ViewCommands(),
        .. DebugCommands(),
        .. MoreCommands(),
        .. StructureCommands(),
        .. PaletteCommands(),
        .. PaneCommands(),
        .. ModeCommands(),
        .. WindowCommands(),
        .. WorkbookCommands(),
        .. TextCommands(),
        .. (IsNotebooks ? [] : new List<PaletteCommand> { new("find.scripts", "Find", "Search in scripts…", () => Toggle(() => _searching = true), "Ctrl+Shift+F") }),
    ];

    private string? NeedsDocument => Front is null ? NoDocument : null;

    private List<PaletteCommand> FileCommands() =>
    [
        new("file.new", "File", $"New {KindWord}… (its name first)", AskNewAsync),
        new("file.newSql", "File", "New SQL file… (its name first)", () => AskNewAsync("sql"), WhyNot: IsNotebooks ? "SQL files are the Scripts page's" : null),
        // The desktop app's Ctrl+N and Ctrl+T run the page's "tabs.new-query" (Layout/DesktopKeys): here, New file.
        new("tabs.new-query", "File", "New file… (pick its type, then its name)", () => _newFileButton?.OpenList() ?? Task.CompletedTask, "Ctrl+N"),
        new("file.open", "File", "Open a notebook or script…", OpenAsync, "Ctrl+O"),
        new("file.save", "File", "Save", SaveFrontAsync, "Ctrl+S", Front is null && Project.Current is null ? NothingSaves : null),
        new("file.saveAs", "File", "Save a copy as…", () => SaveAsAsync(Front), "Ctrl+Shift+S", NeedsDocument),
        new("file.rename", "File", "Rename the document…", () => Front is { } doc ? RenameTabAsync(doc.Key) : Task.CompletedTask,
            WhyNot: NeedsDocument ?? (Front is { CanRename: false } ? TabMenus.RenameElsewhere : null)),
        new("file.close", "File", "Close the document", () => Front is { } doc ? CloseAsync(doc.Key) : Task.CompletedTask, WhyNot: NeedsDocument),
        new("file.exportScript", "File", "Export as one Python script…", () => Front is { } doc ? ExportDocumentAsync(doc, "script") : Task.CompletedTask, WhyNot: NeedsDocument),
        new("file.exportNotebook", "File", "Export as one notebook…", () => Front is { } doc ? ExportDocumentAsync(doc, "notebook") : Task.CompletedTask, WhyNot: NeedsDocument),
    ];

    private List<PaletteCommand> ProjectCommands()
    {
        var none = Project.Current is null ? NoProject : null;
        return
        [
            new("project.new", "Project", "New project…", NewProjectAsync),
            new("project.open", "Project", "Open project…", OpenProjectAsync),
            new("project.save", "Project", "Save the project (its .sab/ state)", SaveProjectAsync, WhyNot: none),
            new("project.saveAll", "Project", "Save the project's documents that have unsaved changes", SaveAllAsync, WhyNot: none),
            new("project.copy", "Project", "Copy the project to another folder…", CopyProjectAsync, WhyNot: none),
            new("project.outline", "Project", "Export outline (ARCHITECTURE.md)", ExportOutlineAsync, WhyNot: none),
            new("project.exportData", "Project", "Export data.py (from data.ipynb)", ExportDataAsync, WhyNot: none),
            new("project.close", "Project", "Close the project", CloseProjectAsync, WhyNot: none),
        ];
    }

    private async Task SaveAllAsync()
    {
        foreach (var doc in _documents.Where(d => d.Dirty && d.Path is not null).ToList())
        {
            await SaveAsync(doc);
        }
    }

    private List<PaletteCommand> RunCommands()
    {
        var notebook = Front?.NotebookView;
        var cell = notebook is null ? NoNotebook : notebook.Selected is null ? NoCell : null;
        return
        [
            new("run.main", "Run", "Run the file, or every cell", () => Front is { } doc ? RunMainAsync(doc) : Task.CompletedTask, "F5", NeedsDocument),
            new("run.statement", "Run", "Run the statement at the cursor, then the next", () => Front?.ScriptView?.RunSelectionAsync() ?? Front?.SqlView?.RunSelectionAsync() ?? Task.CompletedTask, "Ctrl+Enter",
                Front?.ScriptView is null && Front?.SqlView is null ? "A script's command: put a script in front" : null),
            new("run.cell", "Run", "Run the selected cell", () => notebook!.RunSelectedAsync(), "Ctrl+Enter", cell),
            new("run.above", "Run", "Run the cells above", () => notebook!.RunAboveAsync(), WhyNot: cell),
            new("run.below", "Run", "Run this cell and the ones below", () => notebook!.RunBelowAsync(), WhyNot: cell),
            new("run.upTo", "Run", "Run up to here: every cell from the top to the selected one", () => notebook!.RunUpToHereAsync(), WhyNot: cell),
            new("run.interrupt", "Run", "Interrupt", InterruptAsync, WhyNot: Session.Busy ? null : "Nothing is running"),
            new("run.restart", "Run", "Restart the kernel", RestartAsync, WhyNot: Session.Kernel is null ? "The Python session has not started" : null),
        ];
    }

    private List<PaletteCommand> CellCommands()
    {
        if (Front?.NotebookView is not { } nb)
        {
            return [];
        }
        var cell = nb.Selected is null ? NoCell : null;
        Task now(Action act)
        {
            act();
            return Task.CompletedTask;
        }
        return
        [
            new("cell.above", "Cell", "Insert a cell above", nb.InsertAboveAsync, "A"),
            new("cell.below", "Cell", "Insert a cell below", nb.InsertBelowAsync, "B"),
            new("cell.delete", "Cell", "Delete the cell", nb.DeleteSelectedAsync, WhyNot: cell),
            new("cell.undo", "Cell", "Undo a cell's delete or move", nb.UndoAsync, "Z"),
            new("cell.up", "Cell", "Move the cell up", () => nb.MoveSelectedAsync(-1), WhyNot: cell),
            new("cell.down", "Cell", "Move the cell down", () => nb.MoveSelectedAsync(1), WhyNot: cell),
            new("cell.python", "Cell", "Make it a Python cell", () => nb.MakeKindAsync("code"), "Y", cell),
            new("cell.sql", "Cell", "Make it a SQL cell", () => nb.MakeKindAsync("sql"), WhyNot: cell),
            new("cell.markdown", "Cell", "Make it a Markdown cell", () => nb.MakeKindAsync("markdown"), "M", cell),
            new("cell.dax", "Cell", "Make it a DAX cell", () => nb.MakeKindAsync("dax"), WhyNot: cell),
            new("cell.html", "Cell", "Make it an HTML cell", () => nb.MakeKindAsync("html"), WhyNot: cell),
            new("cell.addDax", "Cell", "Add a DAX cell", () => nb.AddCellAsync("dax")),
            new("cell.addHtml", "Cell", "Add an HTML cell", () => nb.AddCellAsync("html")),
            new("cell.duplicate", "Cell", "Duplicate the cell", nb.DuplicateAsync, WhyNot: cell),
            new("cell.copy", "Cell", "Copy the cell (for a paste into a notebook)", () => now(nb.CopySelected), "C", cell),
            new("cell.paste", "Cell", "Paste the copied cell", nb.PasteBelowAsync, "V", NotebookView.HasCopied ? null : "Copy a cell first"),
            new("cell.name", "Cell", "Name the cell…", nb.NameSelectedAsync, WhyNot: cell),
            new("cell.clear", "Cell", "Clear the cell's output", () => now(nb.ClearSelected), WhyNot: cell),
            new("cell.clearAll", "Cell", "Clear every output", () => now(nb.ClearAll)),
            new("cell.toggleOutput", "Cell", "Hide or show the cell's output", () => now(nb.ToggleSelectedOutput), "O", cell),
            new("cell.goTo", "Cell", "Go to a cell by its number", nb.GoToCellAsync),
            new("cell.snippet", "Cell", "Insert a snippet…", () => now(nb.PickSnippet), WhyNot: cell),
            new("notebook.outline", "Notebook", "The Outline: the Markdown headings and the named cells", nb.ToggleOutlineAsync),
            new("view.panel", "View", "Show or hide a panel of the document in front (Outline)", nb.ToggleOutlineAsync),
        ];
    }

    private List<PaletteCommand> DocumentCommands()
    {
        var split = CanSplit(Front) ? null : $"It cannot split: {SplitWhy}";
        var groups = _layout.Groups.Count > 1 ? null : "There is one group: split first";
        return
        [
            new("documents.next", "Documents", "Next document", () => ShowNextAsync(1), "Ctrl+PageDown", NeedsDocument),
            new("documents.previous", "Documents", "Previous document", () => ShowNextAsync(-1), "Ctrl+PageUp", NeedsDocument),
            new("groups.splitRight", "Groups", "Split right: the tab moves to a new group on the right", () => SplitAsync(Front, SplitSide.Right), "Ctrl+\\", split),
            new("groups.splitDown", "Groups", "Split down: the tab moves to a new group below", () => SplitAsync(Front, SplitSide.Down), WhyNot: split),
            new("groups.next", "Groups", "Focus the next group", () => FocusGroupAsync(1), WhyNot: groups),
            new("groups.previous", "Groups", "Focus the previous group", () => FocusGroupAsync(-1), WhyNot: groups),
            new("groups.moveNext", "Groups", "Move the tab to the next group", MoveToNextGroupAsync, WhyNot: groups ?? NeedsDocument),
            new("groups.left", "Groups", "Move the tab left in its row", () => ReorderAsync(-1), WhyNot: NeedsDocument),
            new("groups.right", "Groups", "Move the tab right in its row", () => ReorderAsync(1), WhyNot: NeedsDocument),
        ];
    }

    private List<PaletteCommand> ViewCommands() =>
    [
        new("view.files", "View", "Show or hide the Files pane", ToggleFilesAsync, "Ctrl+B"),
        new("view.blades", "View", "Show or hide the Blades pane", ToggleBladesAsync),
        new("view.full", "View", "Full screen", FullScreenAsync, "F11"),
        new("view.environment", "View", "Go to the Environment", () => Go("environment")),
        new("go.home", "Go", "Home: Projects, in the home window", () => Go("./")),
        new("go.back", "Go", "Back", () => Js.InvokeVoidAsync("history.back").AsTask()),
        new("go.forward", "Go", "Forward", () => Js.InvokeVoidAsync("history.forward").AsTask()),
    ];

    private Task DebugAsync(OpenDocument doc) => GuardAsync(() => doc.ScriptView?.DebugAsync() ?? Task.CompletedTask);

    private List<PaletteCommand> DebugCommands()
    {
        if (Front is not { ScriptView: { } script } doc)
        {
            return [];
        }
        var debug = script.Debugger;
        var paused = debug?.Paused == true ? null : "Not paused at a breakpoint";
        Func<Task> step(string action) => () => debug?.StepAsync(action) ?? Task.CompletedTask;
        return
        [
            new("debug.start", "Debug", "Start debugging", () => DebugAsync(doc), "Ctrl+Shift+D"),
            new("debug.toggle", "Debug", "Toggle breakpoint", () => debug?.ToggleAtCursorAsync() ?? Task.CompletedTask, "F9"),
            new("debug.continue", "Debug", "Continue", step("continue"), "F5", paused),
            new("debug.over", "Debug", "Step over", step("over"), "F10", paused),
            new("debug.into", "Debug", "Step into", step("into"), WhyNot: paused),
            new("debug.out", "Debug", "Step out", step("out"), "Shift+F11", paused),
            new("debug.stop", "Debug", "Stop debugging", () => debug?.StopAsync() ?? Task.CompletedTask, "Shift+F5", debug?.Active == true ? null : "Not debugging"),
        ];
    }

    private Task FocusGroupAsync(int by)
    {
        var group = _layout.NextGroup(by);
        _layout.Focus(group);
        return FollowAddressAsync();
    }

    private Task MoveToNextGroupAsync()
    {
        if (Front is { } doc)
        {
            _layout.MoveTo(doc.Key, _layout.NextGroup(1));
        }
        return FollowAddressAsync();
    }

    private Task ReorderAsync(int by)
    {
        if (Front is { } doc)
        {
            _layout.Reorder(doc.Key, by);
        }
        return Task.CompletedTask;
    }
}
