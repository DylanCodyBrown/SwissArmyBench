using Microsoft.AspNetCore.Components.Web;

using SwissArmyBench.Web.Components;

namespace SwissArmyBench.Web.Pages.Workbench;

// The status bar's Problems (the classic workbenchStatusBar.ts): its count, and a click lists every problem of the
// document in front ("cell 3, line 2: ..."), each a click to its place; Check with Ruff too: install ruff… when the
// document's Python has no Ruff.
public partial class WorkbenchPage
{
    private const int ProblemWordsMax = 120;

    private async Task ProblemsMenuAsync(MouseEventArgs at)
    {
        if (Front is not { } doc)
        {
            return;
        }
        List<(string Place, CodeEditor Editor, Func<int, int, Task> Go)> editors = doc.NotebookView is { } nb
            ? nb.Editors().Select(e => (e.Place, e.Editor, (Func<int, int, Task>)((l, c) => nb.RevealAsync(e.Cell, l, c)))).ToList()
            : (doc.ScriptView?.Editor ?? doc.SqlView?.Editor) is { } script ? [(string.Empty, script, (l, c) => script.RevealAsync(l, c))] : [];
        List<MenuEntry> entries = [];
        var ruff = false;
        foreach (var (place, editor, go) in editors)
        {
            var problems = await editor.ProblemsAsync();
            entries.AddRange(problems.Select(p => new MenuEntry(
                $"{(place.Length > 0 ? $"{place}, " : string.Empty)}line {p.Line}: {Cut(p.Message.Replace('\n', ' '))}", "problem", () => go(p.Line, p.Col))));
            ruff = ruff || await editor.RuffMissingAsync();
        }
        if (entries.Count == 0)
        {
            entries.Add(new MenuEntry("No problems", "check", () => Task.CompletedTask));
        }
        if (ruff)
        {
            entries.Add(MenuEntry.Separator);
            entries.Add(new MenuEntry("Check with Ruff too: install ruff…", "plus", InstallRuffAsync));
        }
        _menu = new ShownMenu("Problems", entries, at.ClientX, at.ClientY - 8 - (entries.Count * 30));
    }

    private static string Cut(string words) => words.Length > ProblemWordsMax ? $"{words[..ProblemWordsMax]}…" : words;

    private Task InstallRuffAsync() => GuardAsync(async () =>
    {
        await EnvironmentApi.InstallAsync("ruff");
        await Notes.SayAsync("Ruff is installed: the code is checked with it too.");
    });
}
