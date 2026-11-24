using System.Text.RegularExpressions;

using SwissArmyBench.Web.Api.Workbench;

namespace SwissArmyBench.Web.Pages.Workbench;

// An error panel's fixes and its In your code (the classic workbenchNotebookErrors.ts): a text replaced in the cell
// that failed, an import line added to the first Python cell, a cell added under it, the cell above that makes a
// name run; a frame's cell selected and its line shown.
public partial class NotebookView
{
    private async Task FixAsync((CellModel Cell, RunErrorFix Fix) asked)
    {
        var (running, fix) = asked;
        switch (fix.Kind)
        {
            case "replace" when fix.Target is { } target && fix.Text is { } text && running.Source.Contains(target, StringComparison.Ordinal):
                running.Source = ReplaceFirst(running.Source, target, text);
                (_selected, _focusNext) = (running, running);
                break;
            case "replace":
                await Notes.SayAsync($"{fix.Target ?? "That"} is no longer in the cell.");
                return;
            case "import" when fix.Line is { } line:
                var first = _kept.Cells.FirstOrDefault(c => c.Kind == "code" && !c.IsAppCell) ?? running;
                first.Source = $"{line}\n{first.Source}";
                (_selected, _focusNext) = (first, first);
                await Notes.SayAsync($"Added to cell {_kept.Cells.IndexOf(first) + 1}");
                break;
            case "cell" when fix.Text is { } code:
                var made = new CellModel { Kind = "code", Source = code, Number = _kept.NextCell++ };
                _kept.Cells.Insert(_kept.Cells.IndexOf(running) + 1, made);
                (_selected, _focusNext, _shape) = (made, made, _shape + 1);
                break;
            case "define" when fix.Name is { } name:
                await RunMakerAsync(running, name);
                return;
            case "table" when fix.Name is { } table:
                // A table open in Tables that the code names: its read-only cell added to this document.
                if (await AddTableAsync(table))
                {
                    await Notes.SayAsync($"Added {table}'s table cell: run the cell again");
                }
                return;
            default:
                await Notes.SayAsync("Fix not available here");
                return;
        }
        await OnChanged.InvokeAsync();
    }

    /// <summary>The cell above the failing one that makes a name (assigns, defines or imports it), run.</summary>
    private async Task RunMakerAsync(CellModel running, string name)
    {
        var makes = new Regex($@"^\s*(?:{Regex.Escape(name)}\s*=|def\s+{Regex.Escape(name)}\b|class\s+{Regex.Escape(name)}\b|(?:from\s+\S+\s+)?import\s+.*\b{Regex.Escape(name)}\b)", RegexOptions.Multiline);
        var maker = _kept.Cells.TakeWhile(c => c != running).LastOrDefault(c => c.Kind == "code" && makes.IsMatch(c.Source));
        if (maker is null)
        {
            await Notes.SayAsync($"No cell above defines {name}");
            return;
        }
        await RunAsync(maker);
        if (!maker.Outputs.Any(o => OutputReader.Type(o) == "error"))
        {
            await Notes.SayAsync($"Ran cell {_kept.Cells.IndexOf(maker) + 1}");
        }
    }

    private static string ReplaceFirst(string text, string target, string by)
    {
        var at = text.IndexOf(target, StringComparison.Ordinal);
        return text[..at] + by + text[(at + target.Length)..];
    }

    /// <summary>A frame's cell (by its run's number, else the cell that failed) selected, its line shown.</summary>
    private async Task GoToFrameAsync((CellModel Cell, RunErrorFrame Frame) asked)
    {
        var (running, frame) = asked;
        if (frame.Where != "cell")
        {
            return;
        }
        var cell = _kept.Cells.FirstOrDefault(c => c.ExecutionCount == frame.Cell) ?? running;
        _selected = cell;
        if (_views.TryGetValue(cell, out var view))
        {
            await view.RevealLineAsync(frame.Line);
        }
    }
}
