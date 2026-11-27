using System.Text.Json;

using SwissArmyBench.Web.Pages.Workbench.Docs;
using SwissArmyBench.Web.State;

namespace SwissArmyBench.Web.Pages.Workbench;

// A text document's tab (the owner, 2026-11-27: "Our markdown reader and inline editor would be a great addition" /
// "html, markdown, and renderable code should get a preview toggle"): its view chosen on the tab's bar and
// remembered by the tab, a block edited in place saved at once, a link in it opened, a diagram's picture saved beside
// its file; and the same for the agent (the palette's view.preview, view.split, view.source, preview.saveSvg,
// preview.savePng, each on the tab in front or the file named: the golden rule).
public partial class WorkbenchPage
{
    private async Task SetTextViewAsync(OpenDocument doc, string view)
    {
        if (!TextFiles.Views.Contains(view) || doc.TextKind is not { HasPreview: true })
        {
            return;
        }
        await (doc.TextView?.CommitAsync() ?? Task.CompletedTask); // a block being edited is written back first
        doc.TextViewChosen = view;
        StateHasChanged();
    }

    /// <summary>A block edited in place, or a task box ticked: the text is the document's, and it is saved at once
    /// (only the changed bytes are written; a file changed on disk since is asked about, as any save).</summary>
    private async Task EditedInPlaceAsync(OpenDocument doc, string text)
    {
        ScriptChanged(doc, text);
        if (doc.Path is { } path)
        {
            await SaveToAsync(doc, path);
        }
    }

    /// <summary>A link in a document to another file: opened on its own page.</summary>
    private async Task OpenLinkedAsync(string path)
    {
        if (path.EndsWith(".ipynb", StringComparison.OrdinalIgnoreCase) != IsNotebooks)
        {
            Nav.NavigateTo($"{(IsNotebooks ? "scripts" : "notebooks")}?path={Uri.EscapeDataString(path)}");
            return;
        }
        await OpenPathAsync(path);
        await FollowAddressAsync();
    }

    private Task SavePictureAsync(OpenDocument doc, string format) => GuardAsync(async () =>
    {
        if (doc.TextView is not { } view)
        {
            return;
        }
        var saved = await view.SavePictureAsync(format);
        await Notes.SayAsync(saved.Written ? $"Saved {FilePaths.Name(saved.Path)} beside it." : $"{FilePaths.Name(saved.Path)} is up to date.");
        await LoadTreeAsync();
    });

    private string? NeedsPreview => Front is { TextKind.HasPreview: true } ? null : "the document in front has no preview";

    private string? NeedsDiagram => Front is { TextKind.Preview: "mermaid" } ? null : "the document in front is not a diagram";

    private List<PaletteCommand> TextCommands() =>
    [
        new("view.preview", "View", "Preview the document (a Markdown file: Read)", () => FrontViewAsync(TextFiles.Preview), WhyNot: NeedsPreview),
        new("view.split", "View", "Split: source beside its preview", () => FrontViewAsync(TextFiles.Split), WhyNot: NeedsPreview),
        new("view.source", "View", "Source: the document's text", () => FrontViewAsync(TextFiles.Source), WhyNot: NeedsPreview),
        new("preview.saveSvg", "View", "Save the diagram as SVG beside its file", () => FrontPictureAsync("svg"), WhyNot: NeedsDiagram),
        new("preview.savePng", "View", "Save the diagram as PNG beside its file", () => FrontPictureAsync("png"), WhyNot: NeedsDiagram),
    ];

    private Task FrontViewAsync(string view) => Front is { } doc ? SetTextViewAsync(doc, view) : Task.CompletedTask;

    private Task FrontPictureAsync(string format) => Front is { } doc ? SavePictureAsync(doc, format) : Task.CompletedTask;

    // The agent's view.* and preview.save* with a file named ({"path"}): its tab brought forward (opened when it is
    // not), then the command on it; the answer says the view the tab is in, or where the picture went.
    private async Task<CommandAnswer?> TextAnswerAsync(string command, JsonElement args)
    {
        if (TextOf(args, "path") is { Length: > 0 } path)
        {
            await OpenPathAsync(path);
            await FollowAddressAsync();
            StateHasChanged();
            await Task.Yield();
        }
        if (Front is not { TextKind.HasPreview: true } doc)
        {
            throw new InvalidOperationException("That document has no preview: Markdown, HTML, SVG, Mermaid and chart specs do.");
        }
        if (command.StartsWith("view.", StringComparison.Ordinal))
        {
            var view = command["view.".Length..];
            await SetTextViewAsync(doc, view);
            return At(new { path = doc.Path, view = doc.TextViewNow });
        }
        if (doc.TextViewNow == TextFiles.Source)
        {
            await SetTextViewAsync(doc, TextFiles.Split); // the picture saved is the diagram as drawn
            await DrawnAsync(doc);
        }
        if (doc.TextView is not { } shown)
        {
            throw new InvalidOperationException("The diagram is not drawn yet: try again.");
        }
        var saved = await shown.SavePictureAsync(command == "preview.savePng" ? "png" : "svg");
        return At(new { path = saved.Path, written = saved.Written, format = saved.Format });
    }

    // A view just switched on is drawn a moment later: waited for briefly before its picture is asked for.
    private const int DrawTries = 20;
    private const int DrawWaitMs = 150;

    private async Task DrawnAsync(OpenDocument doc)
    {
        for (var tried = 0; tried < DrawTries && doc.TextView?.DiagramDrawn != true; tried++)
        {
            StateHasChanged();
            await Task.Delay(DrawWaitMs);
        }
    }
}
