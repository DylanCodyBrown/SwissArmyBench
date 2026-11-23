using Microsoft.AspNetCore.Components;

namespace SwissArmyBench.Web.Pages.Workbench;

// A code app's file as a tab of the Scripts page (the classic workbenchPage.ts openCodeFileDoc, the tab kind "Code
// file"): ?codefile=<path> (the Code App page's file list, New TypeScript file), TypeScript's own language service in
// its editor (CodeFileView), Save writing it back to the code app.
public partial class WorkbenchPage
{
    /// <summary>A code app's file to open as a tab (its path in the code app: src/pages/Orders/page.tsx).</summary>
    [Parameter]
    public string? CodeFile { get; set; }

    private string? CodeFileAddress => Front?.CodeFile is { } file ? $"{Page}?codefile={Uri.EscapeDataString(file)}" : null;

    /// <summary>A code app's file: brought to the front when open, else opened as a tab.</summary>
    private async Task OpenCodeFileAsync(string path)
    {
        if (_documents.FirstOrDefault(d => d.CodeFile == path) is { } open)
        {
            _layout.Show(open.Key);
        }
        else
        {
            AddDocument(new OpenDocument(++_nextKey, false) { CodeFile = path });
        }
        await FollowAddressAsync();
    }

    private async Task SaveCodeFileAsync(OpenDocument doc, CodeFileView view)
    {
        await view.SaveAsync();
        doc.Dirty = false;
        _ = Notes.SayAsync($"Saved {doc.Title}");
    }
}
