using Microsoft.JSInterop;

using SwissArmyBench.Web.State;

namespace SwissArmyBench.Web.Pages.Workbench;

// A document in a window of its own (the classic workbenchPage.ts popOut and moveToMain): Open in its own window opens
// its file in a new window and takes its tab away here (unsaved changes asked about first: they stay in this one);
// in that window, Move to the main window hands it back to the window that opened it and closes.
public partial class WorkbenchPage
{
    private bool _popped;

    private async Task ReadWindowAsync()
    {
        if (_module is not null)
        {
            _popped = await _module.InvokeAsync<bool>("popped");
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
        await _module.InvokeVoidAsync("popOut", AddressOf(doc));
        await CloseAsync(doc.Key, force: true);
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
