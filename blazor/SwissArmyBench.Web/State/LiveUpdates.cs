using System.Text.Json;

using Microsoft.JSInterop;

namespace SwissArmyBench.Web.State;

/// <summary>
/// The live-updates socket (/ws, the same one the classic pages hold): every notice the server broadcasts, raised
/// as <see cref="Changed"/>. The socket itself lives in shell.js (it opens again by itself after the server
/// restarts); this side only hears it.
/// </summary>
public sealed class LiveUpdates : IAsyncDisposable
{
    private readonly IJSRuntime _js;
    private DotNetObjectReference<LiveUpdates>? _self;
    private IJSObjectReference? _socket;

    public LiveUpdates(IJSRuntime js)
    {
        _js = js;
    }

    /// <summary>A notice arrived.</summary>
    public event Action<Notice>? Changed;

    /// <summary>The socket opened or closed (the status bar says when the server cannot be reached).</summary>
    public event Action? ConnectionChanged;

    public bool Connected { get; private set; }

    /// <summary>Open the socket once, as a page of the app (workspace=1: the server counts it as a window).</summary>
    public async Task StartAsync()
    {
        if (_socket is not null)
        {
            return;
        }
        _self = DotNetObjectReference.Create(this);
        _socket = await _js.InvokeAsync<IJSObjectReference>("sab.live", _self, "workspace=1");
    }

    [JSInvokable]
    public void Notice(string text)
    {
        Notice? notice;
        try
        {
            using var parsed = JsonDocument.Parse(text);
            var type = parsed.RootElement.TryGetProperty("type", out var t) ? t.GetString() ?? string.Empty : string.Empty;
            notice = new Notice(type, parsed.RootElement.Clone());
        }
        catch (JsonException)
        {
            return; // not a notice: the server sends only JSON, so a bad frame is dropped
        }
        Changed?.Invoke(notice);
    }

    [JSInvokable]
    public void Opened()
    {
        Connected = true;
        ConnectionChanged?.Invoke();
    }

    [JSInvokable]
    public void Closed()
    {
        Connected = false;
        ConnectionChanged?.Invoke();
    }

    public async ValueTask DisposeAsync()
    {
        if (_socket is not null)
        {
            await _socket.InvokeVoidAsync("stop");
            await _socket.DisposeAsync();
        }
        _self?.Dispose();
    }
}
