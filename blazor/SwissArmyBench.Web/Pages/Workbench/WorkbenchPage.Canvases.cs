using Microsoft.JSInterop;

using SwissArmyBench.Web.Components;
using SwissArmyBench.Web.State;

namespace SwissArmyBench.Web.Pages.Workbench;

// The canvases' New entries (the classic workbenchPage.ts registerCanvasKinds), each offered only where the open
// project's mode names it: New canvas (the Streamlit canvas, its page in a window of its own) and New Excel workbook
// (the Accounting extension's Excel canvas). Neither canvas is drawn by this front end yet (README: Canvas, not yet):
// each opens in the classic front end, as every page this one does not have. The palette's Workbook commands act on a
// workbook in front, which this front end never has.
public partial class WorkbenchPage
{
    private const string NoWorkbook = "no workbook is in front";

    private IReadOnlyList<string> _canvases = [];
    private IReadOnlyList<string> _cellKinds = [];

    private List<MenuEntry> CanvasEntries() =>
    [
        .. _canvases.Contains("streamlit") && IsNotebooks ? [new MenuEntry("New canvas", "page", NewCanvasAsync)] : Array.Empty<MenuEntry>(),
        .. _canvases.Contains("excel") && IsNotebooks ? [new MenuEntry("New Excel workbook", "excel", NewWorkbookAsync)] : Array.Empty<MenuEntry>(),
    ];

    private Task NewCanvasAsync() => Js.InvokeVoidAsync("open", "/streamlit/canvas", "_blank").AsTask();

    private async Task NewWorkbookAsync()
    {
        await Js.InvokeVoidAsync("open", "/notebooks", "_blank");
        await Notes.SayAsync("The Excel canvas opens in the classic front end: New Excel workbook there.");
    }

    private IReadOnlyList<string> _languages = [];

    private static readonly Dictionary<string, string> _languageNames = new() { ["typescript"] = "TypeScript", ["tsx"] = "TSX", ["python"] = "Python" };

    /// <summary>The mode's first language when it is not Python (a code app: TypeScript): New makes a file of it.</summary>
    private string? ScriptLanguage => _languages.FirstOrDefault() is { } first && first != "python" ? first : null;

    private List<MenuEntry> LanguageEntries() => ScriptLanguage is { } language && !IsNotebooks
        ? [new MenuEntry($"New {_languageNames.GetValueOrDefault(language, language)} file", "code", () => NewModeFileAsync(language))]
        : [];

    /// <summary>A code app's new file (in src/shared, or a path under src/pages/&lt;Page&gt;/), opened on the Code App page
    /// (its TypeScript editor is that page's, in the classic front end).</summary>
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
            await Js.InvokeVoidAsync("open", "/workspace?open=codeapp", "_blank");
        });
    }

    private List<PaletteCommand> WorkbookCommands() =>
    [
        new("workbook.new", "Workbook", "New Excel workbook", NewWorkbookAsync,
            WhyNot: _canvases.Contains("excel") ? null : "the open project's mode offers no Excel canvas"),
        new("workbook.play", "Workbook", "Play the workbook", () => Task.CompletedTask, WhyNot: NoWorkbook),
        new("workbook.edit", "Workbook", "Edit the workbook's blocks", () => Task.CompletedTask, WhyNot: NoWorkbook),
        new("workbook.report", "Workbook", "The workbook in front, as it stands", () => Task.CompletedTask, WhyNot: NoWorkbook),
    ];
}
