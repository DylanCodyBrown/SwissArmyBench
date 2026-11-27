using Microsoft.AspNetCore.Components;

using SwissArmyBench.Web.State;

namespace SwissArmyBench.Web.Pages.Workbench;

// What a Notebooks or Scripts page shows, for the agent's app_screen (State/ScreenState): the tab in front and its
// document (path, kind, unsaved), every tab, the panes open, the Python session's word. The cursor's line, the
// problems' count and a notebook's cells on screen are read from the window itself (interop/screen.js); no text
// of a document is ever part of it.
public partial class WorkbenchPage
{
    private bool _onScreen;

    [Inject]
    private ScreenState Screen { get; set; } = default!;

    /// <summary>The page drew: the document in front as a note's objects, and the screen state told to look again.</summary>
    private void ShowFront()
    {
        Shown.Set(DocumentObjects.Of(Front));
        if (!_onScreen)
        {
            _onScreen = true;
            Screen.Show(this, ScreenPart);
        }
        Screen.Touch();
    }

    private void ClearShown()
    {
        Shown.Clear();
        Screen.Hide(this);
    }

    private static Dictionary<string, object?> ScreenTab(OpenDocument doc)
    {
        var tab = new Dictionary<string, object?>
        {
            ["title"] = doc.Title,
            ["path"] = doc.Path ?? doc.CodeFile,
            ["kind"] = doc.KindLabel.ToLowerInvariant(),
            ["dirty"] = doc.Dirty,
            // A text document's view (preview, split, source): which of them the tab is in.
            ["view"] = doc.TextKind is { HasPreview: true } ? doc.TextViewNow : null,
        };
        if (doc.Review.Count > 0)
        {
            tab["comments"] = doc.Review.Count; // the count only: a comment's words are never part of the screen state
        }
        return tab;
    }

    private Dictionary<string, object?> ScreenPart() => new()
    {
        ["tab"] = Front is { } front ? ScreenTab(front) : null,
        ["tabs"] = _documents.Select(ScreenTab).ToList(),
        ["panes"] = new (bool Open, string Name)[] { (_showFiles, "Files"), (_showBlades, "Blades"), (_showExplorer, "Data Explorer"), (_showEnvironment, "Environment") }
            .Where(pane => pane.Open)
            .Select(pane => pane.Name)
            .ToList(),
        ["session"] = Session.Words,
        ["script"] = Front is { IsNotebook: false, IsBlade: false, IsStructure: false, IsWorkbook: false } script
            ? new Dictionary<string, object?> { ["language"] = script.IsSql ? "sql" : script.TextKind?.Language ?? "python", ["running"] = script.SqlView?.Running ?? Session.Busy }
            : null,
    };
}
