using SwissArmyBench.Web.Api;
using SwissArmyBench.Web.Api.Settings;

namespace SwissArmyBench.Web.State;

/// <summary>Beta mode (the classic betaNotes.ts state): on or off, what decided it, what the log holds; read once and
/// again on the beta_changed notice. The status bar's Beta mark and Settings' Beta section read it.</summary>
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

    public Task LoadAsync() => _loading ??= RefreshAsync();

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
