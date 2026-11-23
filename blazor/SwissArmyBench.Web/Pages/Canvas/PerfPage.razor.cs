using Microsoft.AspNetCore.Components;
using Microsoft.JSInterop;

using SwissArmyBench.Web.Api;
using SwissArmyBench.Web.Api.Canvas;

namespace SwissArmyBench.Web.Pages.Canvas;

public partial class PerfPage
{
    // While attached, the session is read again this often.
    private const int ReadMs = 1000;

    private PerfSession? _session;
    private Exception? _error;
    private string _tab = "timeline";
    private int? _picked;
    private string? _savedAs;
    private PeriodicTimer? _timer;

    [Inject]
    private CanvasClient Canvases { get; set; } = default!;

    [Inject]
    private IJSRuntime Js { get; set; } = default!;

    [SupplyParameterFromQuery(Name = "canvas")]
    public string? Canvas { get; set; }

    [SupplyParameterFromQuery(Name = "build")]
    public int? Build { get; set; }

    [SupplyParameterFromQuery(Name = "file")]
    public string? File { get; set; }

    private bool Saved => Build is not null && File is not null;

    private string App => Canvas ?? string.Empty;

    protected override async Task OnInitializedAsync()
    {
        await Js.InvokeVoidAsync("sab.setTitle", Saved ? "Saved session · Performance Analyzer" : "Performance Analyzer");
        if (Saved)
        {
            await ReadAsync();
            return;
        }
        try
        {
            await Canvases.PerfAttachAsync(App);
        }
        catch (ApiException error)
        {
            _error = error;
            return;
        }
        await ReadAsync();
        _ = ReadEverySecondAsync();
    }

    private static IEnumerable<(string Tab, string Words)> Tabs(PerfSession s) =>
    [
        ("timeline", "Timeline"),
        ("calls", "Calls"),
        ("cache", "Cache"),
        ("socket", "Web socket"),
        ("hints", s.Hints.Count > 0 ? $"Hints ({s.Hints.Count})" : "Hints"),
    ];

    private static IReadOnlyList<IReadOnlyList<object>> CallRows(PerfSession s) => s.Calls
        .Select(c => (IReadOnlyList<object>)[c.Rerun?.ToString(System.Globalization.CultureInfo.InvariantCulture) ?? string.Empty, c.Kind, c.Block, c.Connection ?? c.Host ?? c.File ?? string.Empty, c.Rows?.ToString(System.Globalization.CultureInfo.InvariantCulture) ?? string.Empty, PerfWords.Ms(c.Ms)])
        .ToList();

    private static IReadOnlyList<IReadOnlyList<object>> CacheRows(PerfSession s) => s.Caches
        .Select(c => (IReadOnlyList<object>)[c.Name, c.Kind, c.Calls, c.Hits, c.Misses, PerfWords.Ms(c.MissMs)])
        .ToList();

    private static IReadOnlyList<IReadOnlyList<object>> ElementRows(PerfSession s) => (s.Socket?.Elements ?? new Dictionary<string, PerfElement>())
        .Select(e => (IReadOnlyList<object>)[e.Key, e.Value.Count, PerfWords.Size(e.Value.Size)])
        .ToList();

    private static IReadOnlyList<IReadOnlyList<object>> BiggestRows(PerfSession s) => (s.Socket?.Biggest ?? [])
        .Select(m => (IReadOnlyList<object>)[m.Direction, m.Kind, m.Element ?? string.Empty, m.Path ?? string.Empty, PerfWords.Size(m.Size)])
        .ToList();

    private async Task ReadAsync()
    {
        try
        {
            _session = Saved ? await Canvases.SavedPerfAsync(App, Build!.Value, File!) with { Recording = false } : await Canvases.PerfAsync(App);
            _error = null;
        }
        catch (ApiException error)
        {
            _error = error;
        }
    }

    private async Task ReadEverySecondAsync()
    {
        _timer = new PeriodicTimer(TimeSpan.FromMilliseconds(ReadMs));
        try
        {
            while (await _timer.WaitForNextTickAsync())
            {
                await InvokeAsync(async () => { await ReadAsync(); StateHasChanged(); });
            }
        }
        catch (ObjectDisposedException)
        {
            // the window closed
        }
    }

    private async Task AttachAsync(bool on, bool fresh = false)
    {
        try
        {
            await Canvases.PerfAttachAsync(App, on, fresh);
            if (fresh)
            {
                _picked = null;
            }
            await ReadAsync();
        }
        catch (ApiException error)
        {
            _error = error;
        }
    }

    private async Task SaveAsync()
    {
        try
        {
            _savedAs = (await Canvases.PerfSaveAsync(App)).File;
        }
        catch (ApiException error)
        {
            _error = error;
        }
    }

    /// <summary>Closing the window detaches: nothing more is recorded (the owner: only when it is open).</summary>
    public async ValueTask DisposeAsync()
    {
        _timer?.Dispose();
        if (!Saved && Canvas is not null)
        {
            try
            {
                await Canvases.PerfDetachAsync(App);
            }
            catch (ApiException)
            {
                // the launch is gone already
            }
        }
    }
}
