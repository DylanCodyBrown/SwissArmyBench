using SwissArmyBench.Web.Api;
using SwissArmyBench.Web.Api.Settings;

namespace SwissArmyBench.Web.State;

/// <summary>Beta mode on every page (the classic betaNotes.ts state): on or off, what decided it, what the log holds;
/// read once and again on the beta_changed notice. While it is on every right-click menu ends with Leave a note…,
/// which opens the one note form (Layout/BetaNoteHost) about the element right-clicked (its role and words, never a
/// cell's text); the status bar's Beta mark and Settings' Beta section read it too.</summary>
public sealed class BetaState : IDisposable
{
    private readonly SettingsClient _settings;
    private readonly LiveUpdates _live;
    private Task? _loading;

    public BetaState(SettingsClient settings, LiveUpdates live)
    {
        _settings = settings;
        _live = live;
        _live.NoticeArrived += OnNotice;
    }

    public event Action? Changed;

    public BetaStatus? Status { get; private set; }

    public bool On => Status?.On == true;

    /// <summary>The environment decides it for this server: the switch is greyed out.</summary>
    public bool Locked => Status?.SetBy == "environment";

    /// <summary>What a note is being written about, or null when no note form is open.</summary>
    public BetaElement? Noting { get; private set; }

    /// <summary>Whether the open note form should name what was right-clicked last (a menu's Leave a note…).</summary>
    public bool FromRightClick { get; private set; }

    /// <summary>Leave a note… about a place: the note form opens over the page. From a right-click menu the form
    /// names the exact element right-clicked; <paramref name="place"/> is its fallback.</summary>
    public void AskNote(BetaElement place, bool fromRightClick = false)
    {
        Noting = place;
        FromRightClick = fromRightClick;
        Changed?.Invoke();
    }

    public void NoteDone()
    {
        Noting = null;
        FromRightClick = false;
        Changed?.Invoke();
    }

    public Task LoadAsync() => _loading ??= RefreshAsync();

    public Task StartAsync() => RefreshAsync();

    /// <summary>Beta mode on or off; refused with the server's words.</summary>
    public async Task SetAsync(bool on)
    {
        Status = await _settings.SetBetaAsync(on);
        Changed?.Invoke();
    }

    public async Task RefreshAsync()
    {
        try
        {
            Status = await _settings.BetaAsync();
        }
        catch (ApiException)
        {
            Status = null; // an older server: no beta mode
        }
        Changed?.Invoke();
    }

    private void OnNotice(Notice notice)
    {
        if (notice.Type == "beta_changed")
        {
            _ = RefreshAsync();
        }
    }

    public void Dispose() => _live.NoticeArrived -= OnNotice;
}
