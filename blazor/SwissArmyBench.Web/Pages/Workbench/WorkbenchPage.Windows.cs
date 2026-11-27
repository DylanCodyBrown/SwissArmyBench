using Microsoft.AspNetCore.Components;
using Microsoft.JSInterop;

using SwissArmyBench.Web.State;

namespace SwissArmyBench.Web.Pages.Workbench;

// A document in a window of its own, by the app's one pop-out (State/PopOuts.cs; the owner, 2026-11-27): Open in its
// own window opens its file in a new window (unsaved changes asked about first: it opens the file as saved) and its tab
// here stays, blank but for Reattach and Show window (Tabs/GroupView). In that window, Move to the main window (or the
// corner's Reattach) saves what is unsaved, closes it and shows the document here again, read from its file. The
// project's one Python session is the same in both windows.
public partial class WorkbenchPage
{
    private bool _popped;

    [Inject]
    private PopOuts PopOuts { get; set; } = default!;

    private async Task ReadWindowAsync()
    {
        if (_module is not null)
        {
            _popped = PopOuts.Own is not null || await _module.InvokeAsync<bool>("popped");
        }
        if (PopOuts.Own?.StartsWith($"{PopOutKeys.Document}:", StringComparison.Ordinal) == true)
        {
            PopOuts.BeforeClose = SaveUnsavedAsync;
        }
    }

    private string AddressOf(OpenDocument doc) => doc.Path is { } path ? $"{Page}?path={Uri.EscapeDataString(path)}" : Page;

    private async Task PopOutAsync(OpenDocument doc)
    {
        if (_module is null || doc.Path is null)
        {
            return;
        }
        if (doc.Dirty && !await Dialogs.AskYesNoAsync("Open in its own window", $"{doc.Title} has changes that are not saved: its own window opens its file as saved. Save it first?", "Save and open"))
        {
            return;
        }
        if (doc.Dirty)
        {
            await SaveAsync(doc);
        }
        await PopOuts.PopAsync(PopOutKeys.DocumentKey(doc.Path), doc.Title, AddressOf(doc));
    }

    // A popped-out document's window is about to close itself (Reattach): what is unsaved goes to its file first.
    private async Task SaveUnsavedAsync()
    {
        foreach (var doc in _documents.Where(d => d.Dirty && d.Path is not null).ToList())
        {
            await SaveAsync(doc);
        }
    }

    private async Task MoveToMainAsync(OpenDocument doc)
    {
        if (_module is null)
        {
            return;
        }
        if (doc.Dirty)
        {
            await SaveAsync(doc);
        }
        if (PopOuts.Own is not null)
        {
            await PopOuts.ReattachOwnAsync();
            return;
        }
        if (!await _module.InvokeAsync<bool>("moveToMain", AddressOf(doc)))
        {
            _error = new InvalidOperationException("This is the main window, or nothing is in front.");
        }
    }

    private List<PaletteCommand> WindowCommands() =>
    [
        new("doc.popOut", "Documents", "Open the document in its own window", () => Front is { } doc ? PopOutAsync(doc) : Task.CompletedTask,
            WhyNot: Front is null ? "no notebook, script or Streamlit app is in front" : Front.Path is null ? "Save it first: its own window opens its file" : null),
        new("doc.moveToMain", "Documents", "Move the document to the main window", () => Front is { } doc ? MoveToMainAsync(doc) : Task.CompletedTask,
            WhyNot: !_popped || Front is null ? "this is the main window, or nothing is in front" : null),
    ];
}
