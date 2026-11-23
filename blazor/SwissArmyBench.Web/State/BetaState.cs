using SwissArmyBench.Web.Api;
using SwissArmyBench.Web.Api.Settings;

namespace SwissArmyBench.Web.State;

/// <summary>
/// Beta mode on every page (the classic betaNotes.ts): one switch on the server, kept across restarts, followed by
/// its `beta_changed` notice. While it is on every right-click menu ends with Leave a note…, which keeps the user's
/// words, the page and what was right-clicked (its role and words, never a cell's text).
/// </summary>
public sealed class BetaState : IDisposable
{
    private readonly SettingsClient _settings;
    private readonly ApiClient _api;
    private readonly LiveUpdates _live;

    public BetaState(SettingsClient settings, ApiClient api, LiveUpdates live)
    {
        _settings = settings;
        _api = api;
        _live = live;
        _live.NoticeArrived += OnNotice;
    }

    public event Action? Changed;

    public bool On { get; private set; }

    /// <summary>The place a note is being written about ("Menu: Orders"), or null when no note form is open.</summary>
    public string? Noting { get; private set; }

    /// <summary>Leave a note… about a place: the note form opens over the page.</summary>
    public void AskNote(string place)
    {
        Noting = place;
        Changed?.Invoke();
    }

    public void NoteDone()
    {
        Noting = null;
        Changed?.Invoke();
    }

    public async Task StartAsync()
    {
        try
        {
            On = (await _settings.BetaAsync()).On;
        }
        catch (ApiException)
        {
            // An older server: no beta mode.
            On = false;
        }
        Changed?.Invoke();
    }

    /// <summary>A note about one place: the user's words, the page, and the place by its role and words.</summary>
    public Task NoteAsync(string text, string page, string role, string name) =>
        _api.PostAsync("/beta/notes", new { text, page, window = "main", element = new { tag = "div", role, name, text = string.Empty, path = string.Empty } });

    private void OnNotice(Notice notice)
    {
        if (notice.Type == "beta_changed")
        {
            _ = StartAsync();
        }
    }

    public void Dispose() => _live.NoticeArrived -= OnNotice;
}
