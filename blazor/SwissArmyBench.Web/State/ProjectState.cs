using SwissArmyBench.Web.Api;
using SwissArmyBench.Web.Api.Projects;

namespace SwissArmyBench.Web.State;

/// <summary>The open project, as every page shows it (the status bar's name and dot, Home's cards): read at start and
/// again on each project_changed notice.</summary>
public sealed class ProjectState : IDisposable
{
    private readonly ProjectsClient _projects;
    private readonly LiveUpdates _live;

    public ProjectState(ProjectsClient projects, LiveUpdates live)
    {
        _projects = projects;
        _live = live;
        _live.NoticeArrived += OnNotice;
    }

    public event Action? Changed;

    public ProjectInfo? Current { get; private set; }

    /// <summary>Open tables that are not in a project (making one would keep them).</summary>
    public bool Loose { get; private set; }

    /// <summary>A folder another program asked to open while work was unsaved, or null.</summary>
    public string? Asked { get; private set; }

    public async Task RefreshAsync()
    {
        try
        {
            var answer = await _projects.CurrentAsync();
            Current = answer.Project;
            Loose = answer.Loose;
            Asked = answer.Asked;
        }
        catch (ApiException)
        {
            Current = null; // the server did not answer: the status bar says so from the socket
        }
        Changed?.Invoke();
    }

    // An event handler returns nothing: the work goes on as a Task of its own.
    private void OnNotice(Notice notice) => _ = OnNoticeAsync(notice);

    private async Task OnNoticeAsync(Notice notice)
    {
        if (notice.Type is "project_changed" or "project_opened" or "project_closed" or "project_saved")
        {
            await RefreshAsync();
        }
    }

    public void Dispose() => _live.NoticeArrived -= OnNotice;
}
