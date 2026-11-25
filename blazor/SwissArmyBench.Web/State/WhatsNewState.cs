using Microsoft.JSInterop;

using SwissArmyBench.Web.Api.Settings;

namespace SwissArmyBench.Web.State;

/// <summary>
/// What's New (the owner, 2026-11-25: "a what's new page that opens and closes as an overlay when a user update"):
/// whether the window is on show and the releases it shows, newest first. It opens by itself on the first start after
/// an update (the server says so), from Help's What's new and the status bar's version (every release), and when the
/// agent opens it (the whats_new_open notice). The main window only (sab-home), never a window popped out. Closing it
/// marks the running version seen on this computer. Its value raises one Changed.
/// </summary>
public sealed class WhatsNewState : IDisposable
{
    public const string OpenNotice = "whats_new_open";
    public const string MainWindow = "sab-home";

    private readonly SettingsClient _settings;
    private readonly LiveUpdates _live;
    private readonly IJSRuntime _js;
    private bool _main;

    public WhatsNewState(SettingsClient settings, LiveUpdates live, IJSRuntime js)
    {
        _settings = settings;
        _live = live;
        _js = js;
        _live.NoticeArrived += OnNotice;
    }

    public event Action? Changed;

    public bool Open { get; private set; }

    /// <summary>The releases shown, newest first (the first one unfolded).</summary>
    public IReadOnlyList<WhatsNewRelease> Releases { get; private set; } = [];

    /// <summary>The main window asks once as it opens: the window shows itself after an update.</summary>
    public async Task StartAsync()
    {
        _main = await _js.InvokeAsync<string?>("sab.windowName") == MainWindow;
        if (!_main)
        {
            return;
        }
        var state = await _settings.WhatsNewAsync();
        if (state.Open && state.Releases.Count > 0)
        {
            Show(state.Releases);
        }
    }

    /// <summary>Help's What's new and the status bar's version: every release, the newest unfolded.</summary>
    public async Task OpenAsync()
    {
        var state = await _settings.WhatsNewAsync(all: true);
        Show(state.Releases);
    }

    public void Show(IReadOnlyList<WhatsNewRelease> releases)
    {
        Releases = releases;
        Open = true;
        Changed?.Invoke();
    }

    /// <summary>X, Escape, a click outside or Got it: closed, and this version seen.</summary>
    public async Task CloseAsync()
    {
        if (!Open)
        {
            return;
        }
        Open = false;
        Changed?.Invoke();
        await _settings.WhatsNewSeenAsync();
    }

    private void OnNotice(Notice notice)
    {
        if (notice.Type == OpenNotice && _main)
        {
            _ = OpenAsync();
        }
    }

    public void Dispose() => _live.NoticeArrived -= OnNotice;
}
