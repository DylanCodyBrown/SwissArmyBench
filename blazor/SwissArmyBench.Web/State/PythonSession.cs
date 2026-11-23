using SwissArmyBench.Web.Api.Workbench;

namespace SwissArmyBench.Web.State;

/// <summary>
/// The Python session the open document runs in (the classic workbenchKernel.ts and projectSession.ts): the open
/// project's one session for every notebook and script of it, else a loose file's kernel of its own. Its value is
/// the kernel, its Python and its state in words (Not started, Starting…, Ready, Running…); it raises one Changed,
/// and follows the live notices (a session restarted or ended from any window).
/// </summary>
public sealed class PythonSession : IDisposable
{
    private readonly WorkbenchClient _workbench;
    private readonly LiveUpdates _live;
    private string? _forPath;
    private int _running;

    public PythonSession(WorkbenchClient workbench, LiveUpdates live)
    {
        _workbench = workbench;
        _live = live;
        _live.NoticeArrived += OnNotice;
    }

    public event Action? Changed;

    public string? Kernel { get; private set; }

    public string? Python { get; private set; }

    /// <summary>The project's one session (shared by its documents), with the server's words for it.</summary>
    public SessionInfo? Shared { get; private set; }

    public bool Starting { get; private set; }

    public bool Busy => _running > 0;

    /// <summary>What happened to the session last, from the server ("restarted: every variable is cleared").</summary>
    public string? Said { get; private set; }

    public string Words => Starting ? "Starting…" : Kernel is null ? "Not started" : Busy ? "Running…" : "Ready";

    /// <summary>The kernel for a document (started when there is none, or the document is another loose file's).</summary>
    public async Task<string> KernelForAsync(string? path)
    {
        if (Kernel is not null && (Shared is not null || _forPath == path))
        {
            return Kernel;
        }
        Starting = true;
        Changed?.Invoke();
        try
        {
            var started = await _workbench.StartAsync(path);
            Kernel = started.Kernel;
            Python = started.Python;
            Shared = started.Session;
            _forPath = path;
            Said = null;
            return started.Kernel;
        }
        finally
        {
            Starting = false;
            Changed?.Invoke();
        }
    }

    /// <summary>A run began (true) or ended (false): the status bar says Running… while any runs.</summary>
    public void Ran(bool started)
    {
        _running = Math.Max(0, _running + (started ? 1 : -1));
        Changed?.Invoke();
    }

    public async Task InterruptAsync()
    {
        if (Kernel is not null)
        {
            await _workbench.InterruptAsync(Kernel);
        }
    }

    public async Task RestartAsync()
    {
        if (Kernel is not null)
        {
            await _workbench.RestartAsync(Kernel);
        }
    }

    private void OnNotice(Notice notice)
    {
        if (notice.Text("kernel") != Kernel || Kernel is null)
        {
            return;
        }
        if (notice.Type == "session_restarted")
        {
            Python = notice.Text("python") ?? Python;
            Said = notice.Text("words");
            _running = 0;
            Changed?.Invoke();
        }
        else if (notice.Type == "session_ended")
        {
            Kernel = null;
            Shared = null;
            Said = notice.Text("words");
            _running = 0;
            Changed?.Invoke();
        }
    }

    public void Dispose() => _live.NoticeArrived -= OnNotice;
}
