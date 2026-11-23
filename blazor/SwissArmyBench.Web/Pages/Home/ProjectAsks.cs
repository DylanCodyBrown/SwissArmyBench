using SwissArmyBench.Web.Api;
using SwissArmyBench.Web.Api.Projects;
using SwissArmyBench.Web.State;

namespace SwissArmyBench.Web.Pages.Home;

/// <summary>The project's questions (the classic projectFile.ts): a request the server refuses because unsaved work
/// would go (409) asked again in the classic's words ("{name} has unsaved changes." then the question) and sent
/// with discard on OK; a folder that is not a project yet made one on the user's word.</summary>
public static class ProjectAsks
{
    private const int ConflictStatus = 409;

    /// <summary>What would be lost, in words: the project's unsaved changes, or open tables in no project.</summary>
    public static string Lost(ProjectState state) => state.Current is { Dirty: true } project
        ? $"{project.Name} has unsaved changes."
        : state.Loose ? "The open tables are not saved in a project." : "There are unsaved changes.";

    /// <summary>The request; refused for unsaved work, the question, then the request with discard; null when the
    /// user said no.</summary>
    public static async Task<ProjectAnswer?> WithQuestionAsync(Dialogs dialogs, ProjectState state, Func<bool, Task<ProjectAnswer>> post, string title, string question)
    {
        try
        {
            return await post(false);
        }
        catch (ApiException error) when (error.Status == ConflictStatus)
        {
            await state.RefreshAsync();
            return await dialogs.AskYesNoAsync(title, $"{Lost(state)}\n\n{question}", "OK", danger: true) ? await post(true) : null;
        }
    }

    /// <summary>Open project: its folder; a plain folder made a project around its files when the user says so.</summary>
    public static async Task<ProjectAnswer?> OpenAsync(Dialogs dialogs, ProjectState state, ProjectsClient projects, string path)
    {
        var name = BaseName(path);
        var opened = await WithQuestionAsync(dialogs, state, discard => projects.OpenAsync(path, discard), "Open project", $"Let them go and open {name}?");
        if (opened?.NotAProject is { } plain)
        {
            if (!await dialogs.AskYesNoAsync("Open project", $"{BaseName(plain)} is not a project yet.\n\nMake this folder a project? Nothing in it is written over.", "OK"))
            {
                return null;
            }
            opened = await WithQuestionAsync(dialogs, state, discard => projects.OpenAsync(path, discard, make: true), "Open project", $"Let them go and open {name}?");
        }
        await state.RefreshAsync();
        return opened;
    }

    public static async Task<ProjectAnswer?> CloseAsync(Dialogs dialogs, ProjectState state, ProjectsClient projects)
    {
        var closed = await WithQuestionAsync(dialogs, state, discard => projects.CloseAsync(discard), "Close project", "Let them go and close the project?");
        await state.RefreshAsync();
        return closed;
    }

    /// <summary>Another program asked to open a folder (swissarmybench open) while work is unsaved: asked once.</summary>
    public static async Task AnswerAskedAsync(Dialogs dialogs, ProjectState state, ProjectsClient projects, string asked)
    {
        var open = await dialogs.AskYesNoAsync("Open project", $"{Lost(state)}\n\nLet them go and open {BaseName(asked)}?", "OK", danger: true);
        await projects.AnswerAskedAsync(asked, open);
        await state.RefreshAsync();
    }

    public static string BaseName(string path) => path.TrimEnd('/', '\\').Split('/', '\\')[^1];
}
