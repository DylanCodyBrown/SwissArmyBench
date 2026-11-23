using Microsoft.AspNetCore.Components;
using Microsoft.AspNetCore.Components.Web;

using SwissArmyBench.Web.Api;
using SwissArmyBench.Web.Api.Workbench;
using SwissArmyBench.Web.State;

namespace SwissArmyBench.Web.Pages.Workbench;

// The status bar's Python (the classic workbenchStatusBar.ts pythonPicker and projectSession.ts): a project's
// document runs in the project's one Python (its words, a click to its libraries; Make it now or Try again while it
// is missing or failed; a notebook's older environment offered: Add them, Not now); a loose document picks its own
// (this app's, one found, New environment…, Another Python…), its kernel stopped when it changes.
public partial class WorkbenchPage
{
    private const string NewEnvironmentChoice = "__new";
    private const string AnotherPythonChoice = "__other";

    private IReadOnlyList<PythonChoice> _pythons = [];
    private ProjectPythonState? _projectPython;
    private bool _newEnvironment;
    private bool _makingPython;

    [Inject]
    private PythonsClient PythonsApi { get; set; } = default!;

    private async Task LoadPythonsAsync()
    {
        try
        {
            _pythons = (await PythonsApi.PythonsAsync()).Pythons;
            _projectPython = await PythonsApi.ProjectAsync();
        }
        catch (ApiException)
        {
            _pythons = []; // the picker offers this app's own
        }
    }

    private void OnPythonNotice(Notice notice)
    {
        if (notice.Type == "project_python")
        {
            _ = InvokeAsync(async () =>
            {
                await LoadPythonsAsync();
                StateHasChanged();
            });
        }
    }

    /// <summary>A document of the open project runs in the project's one Python session.</summary>
    private bool InProject(OpenDocument doc) =>
        Session.Shared is not null || (Project.Current is { } project && doc.Path is { } path
            && path.Replace('\\', '/').StartsWith(project.Path.Replace('\\', '/').TrimEnd('/') + "/", StringComparison.OrdinalIgnoreCase));

    private string ProjectPythonWords => _projectPython is { Own: true } ? "The project's Python"
        : _projectPython?.Status == "making" ? "This app's Python (the project's is being made)" : "This app's Python";

    private static string PythonName(PythonChoice choice, PythonChoice? own)
    {
        var name = choice == own ? "This app's Python"
            : string.Join('/', System.Text.RegularExpressions.Regex.Replace(choice.Python, @"[\\/](bin[\\/]python[\d.]*|Scripts[\\/]python\.exe)$", string.Empty, System.Text.RegularExpressions.RegexOptions.IgnoreCase)
                .Split('/', '\\', StringSplitOptions.RemoveEmptyEntries).TakeLast(2));
        return $"{name}{(choice.Version is { Length: > 0 } v ? $" ({v})" : string.Empty)}{(choice.Ipykernel ? string.Empty : ", no ipykernel")}";
    }

    private async Task PythonPickedAsync(OpenDocument doc, ChangeEventArgs e)
    {
        var picked = e.Value?.ToString() ?? string.Empty;
        if (picked == NewEnvironmentChoice)
        {
            _newEnvironment = true;
            return;
        }
        if (picked == AnotherPythonChoice)
        {
            if (await Files.ChooseAsync("file", "Choose a Python", FolderOf(doc), "file") is { } python)
            {
                await UsePythonAsync(doc, python);
            }
            return;
        }
        await UsePythonAsync(doc, picked);
    }

    private static string? FolderOf(OpenDocument doc) => doc.Path is { } path ? FilePaths.Folder(path) : null;

    private async Task UsePythonAsync(OpenDocument doc, string python)
    {
        if (!_pythons.Any(p => p.Python == python))
        {
            _pythons = [.. _pythons, new PythonChoice(python, null, true)];
        }
        if (await Session.ChooseAsync(doc.Path, python))
        {
            await Notes.SayAsync("Kernel stopped");
        }
        if (doc.Path is { } path)
        {
            await GuardAsync(() => PythonsApi.RememberAsync(path, python));
        }
    }

    private async Task NewEnvironmentDoneAsync((string Python, IReadOnlyList<string> Imports)? made)
    {
        _newEnvironment = false;
        if (made is not { } environment || Front is not { } doc)
        {
            return;
        }
        await UsePythonAsync(doc, environment.Python);
        if (environment.Imports.Count > 0 && doc.NotebookView is { } notebook)
        {
            await notebook.AddFirstCellAsync("code", string.Join('\n', environment.Imports));
        }
    }

    /// <summary>Make it now, or Try again: the project's .venv made.</summary>
    private async Task MakeProjectPythonAsync()
    {
        _makingPython = true;
        await GuardAsync(async () => _projectPython = await PythonsApi.MakeProjectAsync());
        _makingPython = false;
    }

    private Task AnswerOfferAsync(PythonOffer offer, bool add) =>
        GuardAsync(async () => _projectPython = await PythonsApi.AnswerOfferAsync(offer.Document, add));

    private RenderFragment PythonFragment(OpenDocument doc) => InProject(doc) ? ProjectPythonFragment : LoosePythonFragment(doc);

    private Task OpenProjectLibrariesAsync(MouseEventArgs _) => Go("environment?at=libraries");
}
