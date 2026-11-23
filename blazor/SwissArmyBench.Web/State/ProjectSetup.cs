using System.Text.Json;
using System.Text.RegularExpressions;

using SwissArmyBench.Web.Api;
using SwissArmyBench.Web.Api.Projects;

namespace SwissArmyBench.Web.State;

/// <summary>
/// What the open project needs installed, found as it opens and installed at once (the owner, 2026-11-23): the
/// project_installs notice, whole each time, as the setup bar (Layout/ProjectSetupBar) draws it on every page. The
/// bar is on screen while the pass checks or installs (unless hidden: the status bar's mark brings it back), and once
/// when it is done or failed, until it is closed. Its value raises one Changed.
/// </summary>
public sealed partial class ProjectSetup : IDisposable
{
    public const string Checking = "checking";
    public const string Installing = "installing";
    public const string Done = "done";
    public const string Failed = "failed";

    private readonly ProjectsClient _projects;
    private readonly LiveUpdates _live;
    private bool _closed;

    public ProjectSetup(ProjectsClient projects, LiveUpdates live)
    {
        _projects = projects;
        _live = live;
        _live.NoticeArrived += OnNotice;
    }

    public event Action? Changed;

    /// <summary>The pass as the server last said it, or null before it said anything.</summary>
    public ProjectInstalls? Now { get; private set; }

    /// <summary>The user hid the bar while it runs (it keeps going; the status bar's mark brings it back).</summary>
    public bool Hidden { get; private set; }

    /// <summary>The pass is looking or installing now.</summary>
    public bool Running => Now?.State is Checking or Installing;

    /// <summary>The bar is on screen: running and not hidden, or done or failed until closed.</summary>
    public bool Shown => Now is { } now && (Running ? !Hidden : now.State is Done or Failed && !_closed);

    /// <summary>The bar's determinate value (0 to 100), or null while there is nothing to count yet.</summary>
    public int? Percent => Now is { Total: > 0, State: Installing or Done or Failed } now
        ? (int)Math.Round(Math.Clamp(now.Share, 0, 1) * 100)
        : null;

    public async Task LoadAsync()
    {
        try
        {
            Take(await _projects.InstallsAsync());
        }
        catch (ApiException)
        {
            // an older server: no installs pass
        }
    }

    /// <summary>A state from the server (the notice, or an answer): a new pass shows the bar again.</summary>
    public void Take(ProjectInstalls state)
    {
        var wasRunning = Running;
        Now = state;
        if (Running && !wasRunning)
        {
            Hidden = false;
            _closed = false;
        }
        Changed?.Invoke();
    }

    public void Hide()
    {
        Hidden = true;
        Changed?.Invoke();
    }

    public void Bring()
    {
        Hidden = false;
        Changed?.Invoke();
    }

    /// <summary>The bar closed (done or failed): it stays away until the next pass.</summary>
    public void Close()
    {
        _closed = true;
        Changed?.Invoke();
    }

    /// <summary>Try again: what the project lacks installed in one install.</summary>
    public async Task RunAsync() => Take(await _projects.RunInstallsAsync());

    /// <summary>The pass is installing these, or has just installed them (the one-at-a-time missing-package prompt
    /// keeps quiet for them: it would ask twice).</summary>
    public bool Covers(MissingPackages missing)
    {
        if (Now is not { State: Checking or Installing or Done } now || missing.Packages.Count == 0)
        {
            return false;
        }
        var covered = (now.Packages ?? []).Where(p => p.Status != "failed").Select(p => Key(p.Name)).ToHashSet();
        return missing.Packages.All(p => covered.Contains(Key(p)));
    }

    /// <summary>A library's name as pip compares it (Scikit_Learn is scikit-learn; extras and versions left off).</summary>
    public static string Key(string name) =>
        Separators().Replace(NameOnly().Match(name).Value, "-").ToLowerInvariant();

    [GeneratedRegex("^[A-Za-z0-9][A-Za-z0-9._-]*")]
    private static partial Regex NameOnly();

    [GeneratedRegex("[-_.]+")]
    private static partial Regex Separators();

    private void OnNotice(Notice notice)
    {
        if (notice.Type != "project_installs")
        {
            return;
        }
        if (notice.Body.Deserialize<ProjectInstalls>(ApiClient.Json) is { } state)
        {
            Take(state);
        }
    }

    public void Dispose() => _live.NoticeArrived -= OnNotice;
}
