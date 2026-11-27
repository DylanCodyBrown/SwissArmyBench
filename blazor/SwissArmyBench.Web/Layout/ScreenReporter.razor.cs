using System.Text.Json;

using Microsoft.AspNetCore.Components;
using Microsoft.JSInterop;

using SwissArmyBench.Web.State;

namespace SwissArmyBench.Web.Layout;

/// <summary>
/// The one reporter of every window (MainLayout and WindowLayout): it hears that something may have changed (a
/// page's Touch, screen.js's Seen, the socket opening again), waits <see cref="WaitMs"/> so many changes are one
/// report, puts the state together and sends it only when it differs from the last one sent.
/// </summary>
public partial class ScreenReporter : IAsyncDisposable
{
    private const string ReportType = "screen";

    private string _seen = "{}";
    private string? _sent;
    private bool _waiting;
    private bool _gone;
    private IJSObjectReference? _module;
    private IJSObjectReference? _watch;
    private DotNetObjectReference<ScreenReporter>? _self;

    [Inject]
    private ScreenState Screen { get; set; } = default!;

    [Inject]
    private LiveUpdates Live { get; set; } = default!;

    [Inject]
    private ProjectState Project { get; set; } = default!;

    [Inject]
    private IJSRuntime Js { get; set; } = default!;

    /// <summary>How long changes are gathered before one report goes: four a second at most.</summary>
    [Parameter]
    public int WaitMs { get; set; } = 250;

    protected override void OnInitialized()
    {
        Screen.Changed += Soon;
        Project.Changed += Soon;
        Live.Changed += OnSocket;
    }

    protected override async Task OnAfterRenderAsync(bool firstRender)
    {
        if (!firstRender)
        {
            return;
        }
        try
        {
            _self = DotNetObjectReference.Create(this);
            _module = await Js.InvokeAsync<IJSObjectReference>("import", "./js/screen.js");
            _watch = await _module.InvokeAsync<IJSObjectReference>("watch", _self);
        }
        catch (JSException)
        {
            // No window to read: the pages' own parts are still reported.
        }
        Soon();
    }

    /// <summary>What screen.js read of the window, when it changed (its JSON: names and numbers only).</summary>
    [JSInvokable]
    public void Seen(string json)
    {
        _seen = json;
        Soon();
    }

    // The socket opened (again: the server forgot this window when it closed): the whole state goes once more.
    private void OnSocket()
    {
        if (Live.Connected)
        {
            _sent = null;
            Soon();
        }
    }

    // An event handler returns nothing: the wait and the report go on as a Task of their own.
    private void Soon()
    {
        if (_waiting || _gone)
        {
            return;
        }
        _waiting = true;
        _ = InvokeAsync(ReportLaterAsync);
    }

    private async Task ReportLaterAsync()
    {
        await Task.Delay(WaitMs);
        _waiting = false;
        if (_gone)
        {
            return;
        }
        var report = Report();
        if (report != _sent && await Live.SendAsync(report))
        {
            _sent = report;
        }
    }

    /// <summary>The report as it is sent: what screen.js read, then each page's own part over it.</summary>
    private string Report()
    {
        Dictionary<string, object?> state = new(StringComparer.Ordinal);
        try
        {
            using var seen = JsonDocument.Parse(_seen);
            foreach (var part in seen.RootElement.EnumerateObject())
            {
                state[part.Name] = part.Value.Clone();
            }
        }
        catch (JsonException)
        {
            // Not what screen.js sends: the pages' own parts alone.
        }
        if (Project.Current is { } project)
        {
            state["project"] = project.Name;
        }
        foreach (var (key, value) in Screen.Read())
        {
            state[key] = value;
        }
        return JsonSerializer.Serialize(new Dictionary<string, object?> { ["type"] = ReportType, ["state"] = state });
    }

    public async ValueTask DisposeAsync()
    {
        _gone = true;
        Screen.Changed -= Soon;
        Project.Changed -= Soon;
        Live.Changed -= OnSocket;
        try
        {
            if (_watch is not null)
            {
                await _watch.InvokeVoidAsync("stop");
                await _watch.DisposeAsync();
            }
            if (_module is not null)
            {
                await _module.DisposeAsync();
            }
        }
        catch (JSDisconnectedException)
        {
            // The window is closing: nothing is left to stop.
        }
        _self?.Dispose();
        GC.SuppressFinalize(this);
    }
}
