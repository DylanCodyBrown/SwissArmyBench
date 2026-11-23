using Microsoft.JSInterop;

using SwissArmyBench.Web.Api.App;

namespace SwissArmyBench.Web.State;

/// <summary>
/// The rail's shared state: its names on or off (this computer's choice, rail.json: every window follows), the
/// areas the on extensions add (GET /app/areas), the canvas when a mode offers it, and the Session's unseen count.
/// </summary>
public sealed class RailState : IDisposable
{
    private readonly AppClient _app;
    private readonly IJSRuntime _js;
    private readonly LiveUpdates _live;

    public RailState(AppClient app, IJSRuntime js, LiveUpdates live)
    {
        _app = app;
        _js = js;
        _live = live;
        _live.NoticeArrived += OnNotice;
    }

    public event Action? Changed;

    public bool Names { get; private set; } = true;

    public IReadOnlyList<AreaInfo> ExtensionAreas { get; private set; } = [];

    /// <summary>A mode of this app offers the Streamlit canvas (the Canvas and Widgets areas show).</summary>
    public bool CanvasOn { get; private set; }

    /// <summary>What the agent did that the user has not seen on the Session page yet.</summary>
    public int Unseen { get; private set; }

    public async Task StartAsync()
    {
        var kept = await _js.InvokeAsync<string?>("sab.recall", "railNames");
        await ShowNamesAsync(kept != "0");
        try
        {
            await ShowNamesAsync((await _app.RailAsync()).Labels);
            ExtensionAreas = await _app.AreasAsync();
            CanvasOn = (await _app.ModesAsync()).Modes.Any(m => m.Canvases.Contains("streamlit"));
        }
        catch (Api.ApiException)
        {
            // The server's answer did not come: the rail keeps the remembered choice and the base's areas.
        }
        Changed?.Invoke();
    }

    public async Task SetNamesAsync(bool on)
    {
        await ShowNamesAsync(on);
        var said = await _app.SetRailAsync(on);
        await ShowNamesAsync(said.Labels);
    }

    public void SessionSeen()
    {
        Unseen = 0;
        Changed?.Invoke();
    }

    private async Task ShowNamesAsync(bool on)
    {
        Names = on;
        await _js.InvokeVoidAsync("sab.setRailNames", on);
        await _js.InvokeVoidAsync("sab.remember", "railNames", on ? "1" : "0");
        Changed?.Invoke();
    }

    // An event handler returns nothing: the work goes on as a Task of its own.
    private void OnNotice(Notice notice) => _ = OnNoticeAsync(notice);

    private async Task OnNoticeAsync(Notice notice)
    {
        switch (notice.Type)
        {
            case "rail_changed":
                await ShowNamesAsync(notice.Flag("labels") ?? true);
                break;
            case "session_entry" when notice.Body.TryGetProperty("entry", out var entry)
                && entry.TryGetProperty("actor", out var actor) && actor.GetString() == "agent":
                Unseen++;
                Changed?.Invoke();
                break;
            default:
                break;
        }
    }

    public void Dispose() => _live.NoticeArrived -= OnNotice;
}
