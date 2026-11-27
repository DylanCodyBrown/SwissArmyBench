using System.Text.Json;

using SwissArmyBench.Web.State;

namespace SwissArmyBench.Web.Pages.Workbench;

// Review comments on the open documents (the owner, 2026-11-27): each document's own (OpenDocument.Review, drawn by
// its editors and its ReviewPanel); here the tab's count following them, the question before a tab with unsent
// comments closes, the palette's commands, and the agent's part: it reads the comments waiting ("comments"), leaves
// notes of its own on lines ("comments.add", marked as the agent's) and takes its own back ("comments.remove");
// sending and clearing are the user's only.
public partial class WorkbenchPage
{
    private const string OnlyTheUserSends = "Only the user sends review comments (Send to agent on the document): what they send reaches you through agent_inbox.";

    private void ReviewChanged()
    {
        Screen.Touch();
        StateHasChanged();
    }

    /// <summary>A tab about to close: unsent review comments are asked about first (they live only here), in one
    /// question with its unsaved changes when it has both.</summary>
    private async Task<bool> ReviewMayGoAsync(OpenDocument doc)
    {
        if (doc.Review.Count == 0)
        {
            return true;
        }
        var unsaved = doc.Dirty ? "changes that are not saved and " : string.Empty;
        return await Dialogs.AskYesNoAsync("Close", $"{doc.Title} has {unsaved}{doc.Review.CountWords} for review not yet sent to the agent. Close it and throw them away?", "Close", danger: true);
    }

    private List<PaletteCommand> ReviewCommands()
    {
        var none = Front is null ? NoDocument : Front.Review.Count == 0 ? "This document has no review comments" : null;
        return
        [
            new("review.comment", "Review", "Comment on the selection…", () => Front is { } doc ? doc.Review.AskAsync(ReviewPartInFront(doc)) : Task.CompletedTask, "Ctrl+Alt+M", NeedsDocument),
            new("review.send", "Review", "Send the review comments to the agent", () => Front?.ReviewPanel?.SendAsync() ?? Task.CompletedTask, WhyNot: none),
            new("review.clear", "Review", "Clear the review comments", () => Front?.ReviewPanel?.ClearAsync() ?? Task.CompletedTask, WhyNot: none),
        ];
    }

    private static string ReviewPartInFront(OpenDocument doc) => doc.NotebookView?.Selected is { } cell ? $"cell {cell.Number}" : string.Empty;

    private async Task<CommandAnswer?> ReviewAnswerAsync(string command, JsonElement args)
    {
        switch (command)
        {
            case "comments":
                return ReviewAt(ReviewDocument(args), null);
            case "comments.add":
                return await ReviewAddAsync(ReviewDocument(args), args);
            case "comments.remove":
                return await ReviewRemoveAsync(ReviewDocument(args), args);
            case "review.send":
            case "review.clear":
                throw new InvalidOperationException(OnlyTheUserSends);
            default:
                return null;
        }
    }

    // {"path"}: the open document of that path; none named: the one in front.
    private OpenDocument ReviewDocument(JsonElement args)
    {
        var path = TextOf(args, "path");
        var found = path is { Length: > 0 }
            ? _documents.FirstOrDefault(d => string.Equals(d.ReviewPath.Replace('\\', '/'), path.Replace('\\', '/'), StringComparison.OrdinalIgnoreCase))
            : Front;
        return found ?? throw new InvalidOperationException(path is { Length: > 0 } ? $"{path} is not open on this page: \"documents\" lists what is." : NoDocument);
    }

    private CommandAnswer ReviewAt(OpenDocument doc, object? made) => new(
        new
        {
            document = doc.ReviewPath,
            made,
            comments = doc.Review.Ordered(doc.ReviewParts())
                .Select(c => new { id = c.Id, where = c.Where, line = c.Line, end = c.End, part = c.Part, comment = c.Text, by = c.ByAgent ? "agent" : "user" })
                .ToList(),
        },
        doc.Path,
        doc.Title,
        null);

    // {"line", "end", "comment", "cell"}: the agent's note on whole lines, marked as the agent's.
    private async Task<CommandAnswer?> ReviewAddAsync(OpenDocument doc, JsonElement args)
    {
        if (NumberOf(args, "line") is not { } line || line < 1)
        {
            throw new InvalidOperationException("line is the first line the note covers, from 1.");
        }
        if (TextOf(args, "comment") is not { } words || words.Trim().Length == 0)
        {
            throw new InvalidOperationException("comment is what the note says.");
        }
        var part = NumberOf(args, "cell") is { } cell ? $"cell {cell}" : string.Empty;
        var made = await doc.Review.AddLinesAsync(part, line, Math.Max(NumberOf(args, "end") ?? line, line), words, byAgent: true);
        return ReviewAt(doc, made.Id);
    }

    // {"id"}: one of the agent's own notes taken back; the user's comments are the user's.
    private async Task<CommandAnswer?> ReviewRemoveAsync(OpenDocument doc, JsonElement args)
    {
        if (NumberOf(args, "id") is not { } id || doc.Review.Find(id) is not { } found)
        {
            throw new InvalidOperationException("id is one of this document's comments: \"comments\" lists them.");
        }
        if (!found.ByAgent)
        {
            throw new InvalidOperationException("That comment is the user's: you take back only notes of your own.");
        }
        await doc.Review.RemoveAsync(id);
        return ReviewAt(doc, null);
    }
}
