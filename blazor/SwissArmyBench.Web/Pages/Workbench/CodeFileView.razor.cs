using Microsoft.AspNetCore.Components;
using Microsoft.JSInterop;

using SwissArmyBench.Web.Api;
using SwissArmyBench.Web.Api.PowerApps;
using SwissArmyBench.Web.Components;

namespace SwissArmyBench.Web.Pages.Workbench;

public partial class CodeFileView : IDisposable
{
    // The app's rule is asked this long after typing stops (the classic's 400 ms).
    private const int LintAfterMs = 400;

    // The language service reads at most this many of the project's files (the classic projectFiles' 200).
    private const int MostFiles = 200;

    private static readonly Dictionary<string, string> _languages = new(StringComparer.Ordinal)
    {
        ["typescript"] = "typescript",
        ["tsx"] = "tsx",
        ["javascript"] = "javascript",
        ["json"] = "json",
        ["css"] = "css",
        ["html"] = "html",
        ["markdown"] = "markdown",
    };

    private CodeAppFile? _file;
    private CodeEditor? _editor;
    private string _text = string.Empty;
    private Exception? _error;
    private CancellationTokenSource? _lint;

    [Inject]
    private CodeAppClient CodeApp { get; set; } = default!;

    [Inject]
    private IJSRuntime Js { get; set; } = default!;

    /// <summary>The file as the code app names it (src/pages/Orders/page.tsx).</summary>
    [Parameter, EditorRequired]
    public string Path { get; set; } = string.Empty;

    /// <summary>The text was typed in (the tab's unsaved dot).</summary>
    [Parameter]
    public EventCallback OnChanged { get; set; }

    /// <summary>A key the page acts on (save).</summary>
    [Parameter]
    public EventCallback<string> OnPageKey { get; set; }

    private string EditorLanguage => _languages.GetValueOrDefault(_file?.Language ?? string.Empty, "plaintext");

    protected override async Task OnInitializedAsync()
    {
        try
        {
            _file = await CodeApp.FileAsync(Path);
            _text = _file.Text;
            if (EditorLanguage is "typescript" or "tsx")
            {
                await CodeEditor.TypeScriptProjectAsync(Js, await ProjectFilesAsync(_file.Path));
            }
        }
        catch (ApiException error)
        {
            _error = error;
        }
    }

    protected override async Task OnAfterRenderAsync(bool firstRender)
    {
        if (_editor is not null && _file is not null && _lint is null)
        {
            _lint = new CancellationTokenSource();
            await LintAsync();
        }
    }

    /// <summary>Save: the file written back to the code app.</summary>
    public async Task SaveAsync()
    {
        await CodeApp.SaveFileAsync(Path, _text);
    }

    private async Task ChangedAsync(string text)
    {
        _text = text;
        await OnChanged.InvokeAsync();
        if (_lint is not null)
        {
            await _lint.CancelAsync();
            _lint.Dispose();
        }
        _lint = new CancellationTokenSource();
        try
        {
            await Task.Delay(LintAfterMs, _lint.Token);
            await LintAsync();
        }
        catch (TaskCanceledException)
        {
            // typed again: the next pause asks
        }
    }

    private async Task LintAsync()
    {
        if (_editor is null)
        {
            return;
        }
        try
        {
            await _editor.SetProblemsAsync(await CodeApp.LintAsync(Path, _text));
        }
        catch (ApiException)
        {
            // the rule is a convenience: the code stands without it
        }
    }

    private Task KeyAsync(EditorKey key) => key.Name == "save" ? OnPageKey.InvokeAsync("save") : Task.CompletedTask;

    /// <summary>The project's TypeScript files known to the language service (the one being edited left out: its own
    /// model speaks for it): its generated models and services, and every src/ .ts or .tsx.</summary>
    private async Task<IReadOnlyList<(string Path, string Text)>> ProjectFilesAsync(string except)
    {
        try
        {
            var project = await CodeApp.ProjectAsync();
            var tree = await CodeApp.FilesAsync(false);
            var paths = project.Generated.Select(g => g.Path)
                .Concat(Leaves(tree.Tree).Where(p => p.StartsWith("src/", StringComparison.Ordinal) && (p.EndsWith(".ts", StringComparison.Ordinal) || p.EndsWith(".tsx", StringComparison.Ordinal))))
                .Where(p => p != except)
                .Distinct()
                .Take(MostFiles)
                .ToList();
            var read = await Task.WhenAll(paths.Select(ReadOrNoneAsync));
            return [.. read.OfType<CodeAppFile>().Select(f => (f.Path, f.Text))];
        }
        catch (ApiException)
        {
            return [];
        }
    }

    private async Task<CodeAppFile?> ReadOrNoneAsync(string path)
    {
        try
        {
            return await CodeApp.FileAsync(path);
        }
        catch (ApiException)
        {
            return null;
        }
    }

    private static IEnumerable<string> Leaves(CodeAppTreeNode node) =>
        node.Children is { } children ? children.SelectMany(Leaves) : node.Path.Length > 0 ? [node.Path] : [];

    public void Dispose()
    {
        _lint?.Cancel();
        _lint?.Dispose();
    }
}
