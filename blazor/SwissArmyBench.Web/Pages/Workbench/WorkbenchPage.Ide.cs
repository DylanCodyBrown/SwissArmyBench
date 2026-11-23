using SwissArmyBench.Web.Api.Workbench;
using SwissArmyBench.Web.Components;

namespace SwissArmyBench.Web.Pages.Workbench;

// The Scripts page's IDE moves (the classic workbenchIde.ts): Go to Definition (F12: this file's line, another
// project module opened at it, a library's place said), Find All References (Shift+F12: a list, each a click),
// Rename Symbol (F2: its preview, then Apply; this document's change stays unsaved in its editor), Format Document
// (Shift+Alt+F: Ruff's, or why not), and Search in scripts (Ctrl+Shift+F).
public partial class WorkbenchPage
{
    private string? _ideTitle;
    private IReadOnlyList<IdePlace>? _idePlaces;
    private IdePlan? _idePlan;
    private (OpenDocument Doc, IdeMove Move, string To)? _renaming;
    private bool _searching;
    private (int Key, int Line)? _revealAfter;

    private Task IdeAsync(OpenDocument doc, IdeMove move) => GuardAsync(move.Name switch
    {
        "definition" => () => DefinitionAsync(doc, move),
        "references" => () => ReferencesAsync(doc, move),
        "rename" => () => RenameAsync(doc, move),
        "format" => () => FormatAsync(doc, move),
        _ => () => Task.CompletedTask,
    });

    private async Task DefinitionAsync(OpenDocument doc, IdeMove move)
    {
        var said = await ScriptIde.DefinitionAsync(move.Text, move.Line, move.Column, doc.Path);
        if (said.Definitions.FirstOrDefault() is not { } found)
        {
            await Notes.SayAsync("No definition found here.");
            return;
        }
        if (found.InProject || found.Path is null || SamePath(found.Path, doc.Path))
        {
            await GoToPlaceAsync(found);
            return;
        }
        await Notes.SayAsync($"{found.Name}: {(found.Builtin ? "built in" : $"in {found.Module ?? "a library"}")}, line {found.Line}.");
    }

    private async Task ReferencesAsync(OpenDocument doc, IdeMove move)
    {
        var said = await ScriptIde.ReferencesAsync(move.Text, move.Line, move.Column, doc.Path);
        if (said.References.Count == 0)
        {
            await Notes.SayAsync("No references found.");
            return;
        }
        (_ideTitle, _idePlaces, _idePlan) = ($"References: {said.References[0].Name} ({said.References.Count})", said.References, null);
    }

    private async Task RenameAsync(OpenDocument doc, IdeMove move)
    {
        var word = move.Word;
        var to = await Dialogs.AskTextAsync("Rename", $"Rename {(word.Length > 0 ? word : "the symbol")} to", "New name", word, "Rename");
        if (to is null || to == word || to.Trim().Length == 0)
        {
            return;
        }
        var plan = await ScriptIde.RenamePlanAsync(move.Text, move.Line, move.Column, doc.Path, to);
        (_ideTitle, _idePlaces, _idePlan, _renaming) = ($"Rename {word} to {to}", null, plan, (doc, move, to));
    }

    private async Task ApplyRenameAsync()
    {
        if (_renaming is not { } renaming || _idePlan is not { } plan)
        {
            return;
        }
        var (doc, move, to) = renaming;
        var done = await ScriptIde.RenameAsync(move.Text, move.Line, move.Column, doc.Path, to);
        // This document's own change, in its editor (unsaved: Save writes it).
        var own = plan.Changes?.FirstOrDefault(c => SamePath(c.Key, doc.Path) || doc.Path is null).Value;
        if (own is not null)
        {
            ScriptChanged(doc, own);
        }
        CloseIde();
        await Notes.SayAsync($"Renamed in {done.Written.Count + (own is null ? 0 : 1)} file(s).");
    }

    private async Task FormatAsync(OpenDocument doc, IdeMove move)
    {
        var said = await ScriptIde.FormatAsync(move.Text, Session.Python);
        if (!said.Formatted)
        {
            throw new InvalidOperationException(said.Why ?? "Not formatted.");
        }
        if (said.Changed && said.Text is { } text)
        {
            ScriptChanged(doc, text);
        }
        else
        {
            await Notes.SayAsync("Already formatted.");
        }
    }

    /// <summary>A place's line: in the document in front, else its file opened on this page at the line.</summary>
    private async Task GoToPlaceAsync(IdePlace place)
    {
        CloseIde();
        if (place.Path is { } path && !SamePath(path, Front?.Path))
        {
            await OpenPathAsync(path);
            await FollowAddressAsync();
        }
        if (Front is { } doc)
        {
            _revealAfter = (doc.Key, place.Line);
        }
    }

    private async Task RevealPendingAsync()
    {
        if (_revealAfter is { } reveal && _byKey.TryGetValue(reveal.Key, out var doc) && doc.ScriptView is { } view)
        {
            _revealAfter = null;
            await view.RevealLineAsync(reveal.Line);
        }
    }

    private void CloseIde() => (_ideTitle, _idePlaces, _idePlan, _renaming) = (null, null, null, null);

    private static bool SamePath(string? a, string? b) =>
        a is not null && b is not null && a.Replace('\\', '/') == b.Replace('\\', '/');
}
