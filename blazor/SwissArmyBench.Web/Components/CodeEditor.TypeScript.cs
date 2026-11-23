using Microsoft.AspNetCore.Components;
using Microsoft.JSInterop;

namespace SwissArmyBench.Web.Components;

// TypeScript with Monaco's own language service (the classic lazy/codeEditor.ts typescriptProject and
// typescriptNotebook): a code app's file opened by its path, so its imports resolve among the project's other files;
// a data notebook's cells with the kernel's declarations.
public partial class CodeEditor
{
    /// <summary>The file this editor edits, as its project names it (src/pages/Orders/page.tsx): its model's address
    /// for the TypeScript service. None: a cell or a loose text.</summary>
    [Parameter]
    public string? Path { get; set; }

    /// <summary>The project's own TypeScript files made known to the language service (the one edited left out).</summary>
    public static async Task TypeScriptProjectAsync(IJSRuntime js, IEnumerable<(string Path, string Text)> files)
    {
        await using var module = await js.InvokeAsync<IJSObjectReference>("import", "./js/codeEditor.js");
        await module.InvokeVoidAsync("typescriptProject", files.Select(f => new { path = f.Path, text = f.Text }).ToList());
    }

    /// <summary>A data notebook's kernel declarations known to the language service (once a page).</summary>
    public static async Task TypeScriptNotebookAsync(IJSRuntime js, string declarations)
    {
        await using var module = await js.InvokeAsync<IJSObjectReference>("import", "./js/codeEditor.js");
        await module.InvokeVoidAsync("typescriptNotebook", declarations);
    }

    /// <summary>Problems a page's own rule found, marked in the code (a code app's pages rule); each a
    /// {line, col, endLine, endCol, message, hover, severity} object as the server answered it.</summary>
    public async Task SetProblemsAsync(IReadOnlyList<System.Text.Json.JsonElement> problems)
    {
        if (_editor is not null)
        {
            await _editor.InvokeVoidAsync("setProblems", problems);
        }
    }
}
