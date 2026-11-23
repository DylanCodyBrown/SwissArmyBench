using Microsoft.JSInterop;

using SwissArmyBench.Web.Components;
using SwissArmyBench.Web.State;

namespace SwissArmyBench.Web.Pages.Workbench;

// The canvases' New entries (the classic workbenchPage.ts registerCanvasKinds), each offered only where the open
// project's mode names it: New canvas (the Streamlit canvas, its page in a window of its own) and New Excel workbook
// (the Accounting extension's Excel canvas, a tab of kind workbook on this page, the classic openWorkbook). The
// palette's Workbook commands act on the workbook tab in front.
public partial class WorkbenchPage
{
    private const string NoWorkbook = "no workbook is in front";

    private string? WorkbookInFront => Front is { IsWorkbook: true } ? null : NoWorkbook;

    private IReadOnlyList<string> _canvases = [];
    private IReadOnlyList<string> _cellKinds = [];

    // The cell kinds another kernel runs, as the open project's mode declares them (a code app's data notebook).
    private IReadOnlyDictionary<string, SwissArmyBench.Web.Api.App.CellRoute> _routes = new Dictionary<string, SwissArmyBench.Web.Api.App.CellRoute>();

    private List<MenuEntry> CanvasEntries() =>
    [
        .. _canvases.Contains("streamlit") && IsNotebooks ? [new MenuEntry("New canvas", "page", NewCanvasAsync)] : Array.Empty<MenuEntry>(),
        .. _canvases.Contains("excel") && IsNotebooks ? [new MenuEntry("New Excel workbook", "excel", NewWorkbookAsync)] : Array.Empty<MenuEntry>(),
    ];

    // The Canvas in a window of its own (the classic opens /streamlit/canvas there): its landing offers New canvas.
    private Task NewCanvasAsync() => Js.InvokeVoidAsync("open", "canvas", "_blank").AsTask();

    /// <summary>New Excel workbook: an untitled design as a tab (its title the project's name, else the tab's).</summary>
    private Task NewWorkbookAsync()
    {
        var untitled = NextUntitled();
        var tab = untitled > 1 ? $"Untitled workbook {untitled}" : "Untitled workbook";
        AddDocument(new OpenDocument(++_nextKey, false) { IsWorkbook = true, Untitled = untitled, WorkbookTitle = Project.Current?.Name ?? tab });
        return Task.CompletedTask;
    }

    /// <summary>A workbook's design (a .design.json file) opened as a tab, or brought to the front.</summary>
    private void OpenWorkbook(string path)
    {
        if (_documents.FirstOrDefault(d => d.IsWorkbook && string.Equals(d.Path, path, StringComparison.OrdinalIgnoreCase)) is { } open)
        {
            _layout.Show(open.Key);
            return;
        }
        AddDocument(new OpenDocument(++_nextKey, false) { IsWorkbook = true, Path = path });
    }

    private Task OpenWorkbookAsync(string path)
    {
        OpenWorkbook(path);
        return FollowAddressAsync();
    }

    private Task WorkbookSavedAsync(OpenDocument doc, string path)
    {
        doc.Path = path;
        doc.Dirty = false;
        return FollowAddressAsync();
    }

    private Task FrontWorkbookAsync(Func<SwissArmyBench.Web.Pages.Accounting.WorkbookPage, Task> act) =>
        Front?.WorkbookView is { } view ? act(view) : Task.CompletedTask;

    private IReadOnlyList<string> _languages = [];

    private static readonly Dictionary<string, string> _languageNames = new() { ["typescript"] = "TypeScript", ["tsx"] = "TSX", ["python"] = "Python" };

    /// <summary>The mode's first language when it is not Python (a code app: TypeScript): New makes a file of it.</summary>
    private string? ScriptLanguage => _languages.FirstOrDefault() is { } first && first != "python" ? first : null;

    private List<MenuEntry> LanguageEntries() => ScriptLanguage is { } language && !IsNotebooks
        ? [new MenuEntry($"New {_languageNames.GetValueOrDefault(language, language)} file", "code", () => NewModeFileAsync(language))]
        : [];

    /// <summary>A code app's new file (in src/shared, or a path under src/pages/&lt;Page&gt;/), opened here as a tab
    /// with TypeScript's own language service (the classic newModeFile, then openCodeFileDoc).</summary>
    private async Task NewModeFileAsync(string language)
    {
        var ending = language == "tsx" ? ".tsx" : ".ts";
        if (await Dialogs.AskTextAsync($"New {_languageNames.GetValueOrDefault(language, language)} file (in src/shared, or a path under src/pages/<Page>/)",
            "The file's name.", "Name", $"module{ending}", "Make it") is not { Length: > 0 } name)
        {
            return;
        }
        var clean = name.Trim().Replace('\\', '/').TrimStart('/');
        if (clean.Contains("..", StringComparison.Ordinal))
        {
            _error = new InvalidOperationException("A file's name, such as orders.ts.");
            return;
        }
        var file = clean.EndsWith(".ts", StringComparison.Ordinal) || clean.EndsWith(".tsx", StringComparison.Ordinal) ? clean : $"{clean}{ending}";
        var path = file.StartsWith("src/", StringComparison.Ordinal) ? file : $"src/shared/{file}";
        await GuardAsync(async () =>
        {
            if (await Workbench.CodeFileThereAsync(path))
            {
                throw new InvalidOperationException($"{path} is there already: open it from the Code App page.");
            }
            await Workbench.NewCodeFileAsync(path);
            await OpenCodeFileAsync(path);
        });
    }

    private List<PaletteCommand> WorkbookCommands() =>
    [
        new("workbook.new", "Workbook", "New Excel workbook", NewWorkbookAsync,
            WhyNot: _canvases.Contains("excel") ? null : "the open project's mode offers no Excel canvas"),
        new("workbook.play", "Workbook", "Play the workbook", () => FrontWorkbookAsync(w => w.PlayAsync()), WhyNot: WorkbookInFront),
        new("workbook.edit", "Workbook", "Edit the workbook's blocks", () => FrontWorkbookAsync(w =>
        {
            w.Edit();
            return ShowHelp("The workbook in front", w.Report());
        }), WhyNot: WorkbookInFront),
        new("workbook.report", "Workbook", "The workbook in front, as it stands", () => FrontWorkbookAsync(w => ShowHelp("The workbook in front", w.Report())), WhyNot: WorkbookInFront),
    ];
}
