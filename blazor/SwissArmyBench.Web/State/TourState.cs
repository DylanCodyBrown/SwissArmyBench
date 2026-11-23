using Microsoft.JSInterop;

namespace SwissArmyBench.Web.State;

/// <summary>
/// The first-time tour (the classic tour.ts and tourButton.ts): whether it is on show, and whether this browser has
/// seen it ("New here? Take the tour" until it is opened once or put away with Not now; kept in this browser only).
/// </summary>
public sealed class TourState
{
    private const string SeenKey = "tour.seen";

    private readonly IJSRuntime _js;

    public TourState(IJSRuntime js)
    {
        _js = js;
    }

    public event Action? Changed;

    public bool Open { get; private set; }

    /// <summary>Opened once, or Not now: the "New here?" bubble is gone for good in this browser.</summary>
    public bool Seen { get; private set; } = true;

    public async Task StartAsync()
    {
        Seen = await _js.InvokeAsync<string?>("sab.recall", SeenKey) is { Length: > 0 };
        Changed?.Invoke();
    }

    public async Task OpenTourAsync()
    {
        await MarkSeenAsync();
        Open = true;
        Changed?.Invoke();
    }

    public async Task MarkSeenAsync()
    {
        Seen = true;
        await _js.InvokeVoidAsync("sab.remember", SeenKey, "1");
        Changed?.Invoke();
    }

    public void Close()
    {
        Open = false;
        Changed?.Invoke();
    }
}
