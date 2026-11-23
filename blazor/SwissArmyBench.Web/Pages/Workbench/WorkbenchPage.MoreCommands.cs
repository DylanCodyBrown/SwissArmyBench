using Microsoft.JSInterop;

using SwissArmyBench.Web.Components;

namespace SwissArmyBench.Web.Pages.Workbench;

// The palette's other commands (the classic workbenchCommandList.ts): the console's, the data area's, the documents'
// and groups', the run's from or to the cursor, Stop the Python session, the view's (code size, layouts, panes), and
// Help (the keyboard shortcuts and every command, help on the name at the cursor).
public partial class WorkbenchPage
{
    private const int BaseCodePx = 13;
    private int _codePx = BaseCodePx;
    private string? _helpTitle;
    private string? _helpText;
    private bool _newBlade;

    private List<WorkbenchCommand> MoreCommands()
    {
        var script = Front?.ScriptView;
        var noScript = script is null ? "A script's console: put a script in front" : null;
        var notebook = Front?.NotebookView;
        var noCell = notebook is null ? NoNotebook : notebook.Selected is null ? NoCell : null;
        return
        [
            new("console.clear", "Console", "Clear the console", () => Toggle(() => script?.ClearConsole()), Disabled: noScript),
            new("console.go", "Console", "Go to the console", () => script?.FocusConsoleAsync() ?? Task.CompletedTask, Disabled: noScript),
            new("console.run", "Console", "Run code in the console", RunInConsoleAsync, Disabled: noScript),
            new("console.shows", "Console", "What the console shows", () => ShowHelp("The console", script?.ConsoleText ?? string.Empty), Disabled: noScript),
            new("data.addConnection", "Data", "Add connection…", () => Go("connections?add=1")),
            new("data.addApi", "Data", "Add API…", () => Go("apis")),
            new("data.browse", "Data", "Browse a connection's tables", () => Go("catalog")),
            new("data.blades", "Data", "Show the blades and connections", () => Toggle(() => _showBlades = true)),
            new("data.closeBlades", "Data", "Close the catalog or the blades beside the Data Explorer", () => Toggle(() => _showBlades = false)),
            new("documents.show", "Documents", "Show a document", ShowDocumentMenuAsync, Disabled: NeedsDocument),
            new("documents.open", "Documents", "What is open", () => ShowHelp("What is open", string.Join('\n', _documents.Select(d => $"{d.KindLabel}: {d.Path ?? d.Title}{(d.Dirty ? " (unsaved)" : string.Empty)}")))),
            new("documents.front", "Documents", "The front document's text or cells", FrontTextAsync, Disabled: NeedsDocument),
            new("file.newBlade", "File", "New blade", () => Toggle(() => _newBlade = true), Disabled: IsNotebooks ? "A blade opens on the Scripts page" : null),
            new("file.newCanvas", "File", "New canvas (the Canvas page)", () => Go("canvas")),
            new("file.closeFront", "File", "Close the document in front (the window when none is open)", CloseFrontAsync),
            new("groups.focus", "Groups", "Focus a group", () => GroupMenuAsync(false), Disabled: _layout.Groups.Count > 1 ? null : "There is one group: split first"),
            new("groups.moveTo", "Groups", "Move a tab to another group", () => GroupMenuAsync(true), Disabled: _layout.Groups.Count > 1 ? NeedsDocument : "There is one group: split first"),
            new("run.cursorToEnd", "Run", "Run from the cursor to the end", () => notebook!.RunBelowAsync(), Disabled: noCell),
            new("run.topToCursor", "Run", "Run from the top to the cursor", () => notebook!.RunUpToHereAsync(), Disabled: noCell),
            new("run.stop", "Run", "Stop the Python session", StopSessionAsync, Disabled: Session.Kernel is null ? "The Python session has not started" : null),
            new("view.codeSize", "View", "Code size", CodeSizeAsync, Disabled: noScript),
            new("view.sourceOnly", "View", "Layout: source only", () => LayoutAsync(false), "Ctrl+Shift+1"),
            new("view.standard", "View", "Layout: standard", () => LayoutAsync(true)),
            new("view.wideData", "View", "Layout: wide data", () => LayoutAsync(true)),
            new("view.environment2", "View", "Show or hide the Environment", () => Go("environment")),
            new("view.readEnvironment", "View", "Read the Environment again (its rows: tables, variables, structures, settings)", () => Go("environment")),
            new("help.keys", "Help", "Keyboard shortcuts", () => ShowHelp("Keyboard shortcuts", Listing(Commands().Where(c => c.Keys is not null)))),
            new("help.every", "Help", "Every command and its arguments", () => ShowHelp("Every command", Listing(Commands()))),
        ];
    }

    private static string Listing(IEnumerable<WorkbenchCommand> commands) =>
        string.Join('\n', commands.Select(c => $"{c.Group}: {c.Label}{(c.Keys is { } k ? $"   {k}" : string.Empty)}"));

    private Task ShowHelp(string title, string text)
    {
        (_helpTitle, _helpText) = (title, text.Length == 0 ? "Nothing." : text);
        return Task.CompletedTask;
    }

    private async Task RunInConsoleAsync()
    {
        if (await Dialogs.AskTextAsync("Run code in the console", "A line of Python, run in the document's session.", "Code", string.Empty, "Run") is { Length: > 0 } code)
        {
            await (Front?.ScriptView?.RunInConsoleAsync(code) ?? Task.CompletedTask);
        }
    }

    private Task ShowDocumentMenuAsync()
    {
        var entries = _documents.Select(d => new MenuEntry(d.Title, d.IsBlade ? "bolt" : d.IsNotebook ? "notebook" : "code", () => ShowAsync(d.Key))).ToList();
        _menu = new ShownMenu("Show a document", entries, 240, 120);
        return Task.CompletedTask;
    }

    private Task GroupMenuAsync(bool move)
    {
        var entries = _layout.Groups.Select((g, i) => new MenuEntry($"Group {i + 1}", "columns", () =>
        {
            if (move && Front is { } doc)
            {
                _layout.MoveTo(doc.Key, g);
            }
            else
            {
                _layout.Focus(g);
            }
            return FollowAddressAsync();
        })).ToList();
        _menu = new ShownMenu(move ? "Move a tab to another group" : "Focus a group", entries, 240, 120);
        return Task.CompletedTask;
    }

    private async Task FrontTextAsync()
    {
        if (Front is not { } doc)
        {
            return;
        }
        var text = doc.NotebookView is { } nb
            ? string.Join("\n\n", nb.ToSave().Cells.Select(c => $"# [{c.Number}] {c.Kind}\n{c.Source}"))
            : doc.ScriptText;
        await ShowHelp(doc.Title, text);
    }

    private Task CloseFrontAsync() => Front is { } doc ? CloseAsync(doc.Key) : Js.InvokeVoidAsync("history.back").AsTask();

    private async Task StopSessionAsync()
    {
        if (Session.Shared is not null && !await Dialogs.AskYesNoAsync("Stop", "Stop the project's Python session? Every variable is gone, for every notebook and script of the project. The next Run starts a new one.", "Stop"))
        {
            return;
        }
        var shared = Session.Shared is not null;
        await Session.StopAsync();
        await Notes.SayAsync(shared ? "The project's Python session stopped" : "Kernel stopped");
    }

    private async Task CodeSizeAsync()
    {
        if (await Dialogs.AskTextAsync("Code size", "The code's size, in percent (100 is its usual size).", "Code size", $"{_codePx * 100 / BaseCodePx}", "Set") is { } typed
            && int.TryParse(typed.Trim().TrimEnd('%'), out var percent))
        {
            _codePx = Math.Clamp(percent * BaseCodePx / 100, 8, 40);
            await (Front?.ScriptView?.SetCodeSizeAsync(_codePx) ?? Task.CompletedTask);
        }
    }

    /// <summary>Layout: source only (the panes put away) or standard (the Files pane back).</summary>
    private Task LayoutAsync(bool standard)
    {
        (_showFiles, _showBlades) = (standard, false);
        return Task.CompletedTask;
    }
}
