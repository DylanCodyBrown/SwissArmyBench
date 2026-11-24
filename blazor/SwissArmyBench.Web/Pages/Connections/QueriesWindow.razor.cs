using System.Globalization;

using Microsoft.AspNetCore.Components;
using Microsoft.AspNetCore.Components.Web;
using Microsoft.JSInterop;

using SwissArmyBench.Web.Api;
using SwissArmyBench.Web.Api.Connections;
using SwissArmyBench.Web.State;

namespace SwissArmyBench.Web.Pages.Connections;

public sealed partial class QueriesWindow : IDisposable
{
    private const int SecondsInMinute = 60;
    private const int MinutesInHour = 60;

    private static readonly string[] _headings = ["Connection", "Who", "What", "State", "Started", "Elapsed", "Rows", string.Empty];
    private static readonly string[] _finishedHeadings = ["Connection", "Who", "What", "Result", "Took", "Rows", "Ended"];

    private QueriesListing _listing = new([], [], [], string.Empty, 0);
    private IReadOnlyList<string> _names = [];
    private string? _connection;
    private double _offset; // the server's clock less this page's (the elapsed time ticks here)
    private string? _selected;
    private string? _opened;
    private string? _openedConnection;
    private QuerySql? _sql;
    private bool _noSql;
    private bool _restarted;
    private string _shownStart = string.Empty;
    private Exception? _error;
    private Timer? _ticker;
    private bool _again;
    private Task? _asking;

    [Inject]
    private QueriesClient Queries { get; set; } = default!;

    [Inject]
    private LiveUpdates Live { get; set; } = default!;

    [Inject]
    private Dialogs Dialogs { get; set; } = default!;

    [Inject]
    private Notes Notes { get; set; } = default!;

    [Inject]
    private NavigationManager Nav { get; set; } = default!;

    [Inject]
    private IJSRuntime Js { get; set; } = default!;

    /// <summary>The connection whose queries it shows (null: every connection's).</summary>
    [Parameter]
    public string? Connection { get; set; }

    /// <summary>The Queries window for a connection (or every one's), a window of its own reused by its name.</summary>
    public static async Task OpenAsync(IJSRuntime js, Notes notes, string? connection)
    {
        var url = connection is null ? "connections?queries=" : $"connections?queries={Uri.EscapeDataString(connection)}";
        var name = $"sab-queries-{string.Concat((connection ?? "all").Select(c => char.IsAsciiLetterOrDigit(c) || c is '_' or '-' ? c : '_'))}";
        if (!await js.InvokeAsync<bool>("sab.openWindow", url, name, "popup,width=1120,height=720"))
        {
            notes.Error(new ApiException(0, new Refusal("The browser blocked the Queries window."), string.Empty));
        }
    }

    private IReadOnlyList<RunningQuery> Shown => _listing.Queries.Where(q => Same(q.Connection)).ToList();

    private IReadOnlyList<FinishedQuery> FinishedShown => _listing.Finished.Where(f => Same(f.Connection)).ToList();

    private bool Same(string name) => _connection is null || string.Equals(name, _connection, StringComparison.CurrentCultureIgnoreCase);

    private string CountWords
    {
        get
        {
            if (_connection is not null)
            {
                return _listing.Connections.FirstOrDefault(c => Same(c.Connection))?.FullWords ?? "Running 0";
            }
            var running = _listing.Queries.Count(q => q.State == "running");
            var waiting = _listing.Queries.Count - running;
            var agent = _listing.Queries.Count(q => q.State == "running" && q.Caller == "agent");
            return $"Running {running}{(waiting > 0 ? $" · {waiting} waiting" : string.Empty)} · agent {agent}";
        }
    }

    protected override async Task OnInitializedAsync()
    {
        _connection = Connection;
        Live.NoticeArrived += OnNotice;
        _ticker = new Timer(_ => InvokeAsync(StateHasChanged), null, 1000, 1000);
        try
        {
            _names = (await Queries.SlotsAsync()).Select(s => s.Connection).ToList();
        }
        catch (ApiException)
        {
            // the listing says it
        }
        if (_connection is { } named && !_names.Any(n => string.Equals(n, named, StringComparison.CurrentCultureIgnoreCase)))
        {
            _names = [named, .. _names];
        }
        await RefreshAsync();
    }

    private Task PickAsync(ChangeEventArgs e)
    {
        _connection = e.Value?.ToString() is { Length: > 0 } picked ? picked : null;
        var url = _connection is null ? "connections?queries=" : $"connections?queries={Uri.EscapeDataString(_connection)}";
        Nav.NavigateTo(url, replace: true);
        return Js.InvokeVoidAsync("sab.setTitle", $"{_connection ?? "All connections"} · Queries").AsTask();
    }

    /// <summary>The list asked again (never polled): once at a time, once more if a notice came meanwhile.</summary>
    private async Task RefreshAsync()
    {
        if (_asking is not null)
        {
            _again = true;
            await _asking;
            return;
        }
        _asking = AskAsync();
        await _asking;
        _asking = null;
        if (_again)
        {
            _again = false;
            await RefreshAsync();
        }
    }

    private async Task AskAsync()
    {
        try
        {
            var got = await Queries.QueriesAsync();
            _offset = got.Now - DateTimeOffset.UtcNow.ToUnixTimeMilliseconds() / 1000.0;
            if (_shownStart.Length > 0 && got.Started != _shownStart && _listing.Queries.Count > 0)
            {
                // The app restarted: what this window showed running or waiting ended with it.
                _restarted = true;
                var ended = _listing.Queries.Select(q => new FinishedQuery(q.Id, q.Connection, q.Who, q.What, q.Targets, "ended", "the app restarted", got.Now, ElapsedOf(q)));
                got = got with { Finished = [.. ended, .. got.Finished] };
            }
            _shownStart = got.Started;
            _listing = got;
            if (_selected is not null && !Shown.Any(q => q.Id == _selected))
            {
                _selected = Shown.FirstOrDefault()?.Id;
            }
            _error = null;
        }
        catch (ApiException error)
        {
            _error = error;
        }
        StateHasChanged();
    }

    private double ElapsedOf(RunningQuery q) => DateTimeOffset.UtcNow.ToUnixTimeMilliseconds() / 1000.0 + _offset - (q.StartedAt ?? q.QueuedAt);

    private static string StateWords(RunningQuery q) => q.State == "waiting" ? $"Waiting · {Ordinal(q.Place ?? 1)} in line" : "Running";

    private static string Ordinal(int n)
    {
        var tens = n % 100;
        var suffix = tens is >= 11 and <= 13 ? "th" : (n % 10) switch { 1 => "st", 2 => "nd", 3 => "rd", _ => "th" };
        return $"{n}{suffix}";
    }

    private static string Clock(double seconds)
    {
        var s = (int)Math.Max(0, Math.Floor(seconds));
        if (s < SecondsInMinute)
        {
            return $"{s} s";
        }
        var m = s / SecondsInMinute;
        return m < MinutesInHour ? $"{m} min {s % SecondsInMinute} s" : $"{m / MinutesInHour} h {m % MinutesInHour} min";
    }

    private static string At(double epoch) => DateTimeOffset.FromUnixTimeMilliseconds((long)(epoch * 1000)).ToLocalTime().ToString("T", CultureInfo.CurrentCulture);

    private static string OutcomeWords(string outcome) => outcome switch
    {
        "ok" => "OK",
        "cancelled" => "Cancelled",
        "failed" => "Failed",
        "timed out" => "Timed out",
        "ended" => "Ended",
        _ => outcome,
    };

    private Task ClickAsync(RunningQuery q)
    {
        _selected = q.Id;
        return ToggleAsync(q);
    }

    /// <summary>The opened query's SQL, as the server formatted it (asked only when opened); again: closed.</summary>
    private async Task ToggleAsync(RunningQuery q)
    {
        if (_opened == q.Id)
        {
            (_opened, _sql, _noSql) = (null, null, false);
            return;
        }
        (_opened, _openedConnection, _sql, _noSql) = (q.Id, q.Connection, null, !q.HasSql);
        if (!q.HasSql)
        {
            return;
        }
        try
        {
            var sql = await Queries.SqlAsync(q.Id);
            if (_opened == q.Id)
            {
                _sql = sql;
            }
        }
        catch (ApiException error)
        {
            _error = error;
        }
    }

    private async Task CancelAsync(RunningQuery q)
    {
        try
        {
            await Queries.CancelAsync(q.Id);
        }
        catch (ApiException error)
        {
            _error = error;
        }
    }

    private async Task OpenSourceAsync(RunningQuery q)
    {
        if (q.Source?.Document is { } document)
        {
            var page = document.EndsWith(".py", StringComparison.OrdinalIgnoreCase) ? "scripts" : "notebooks";
            await Js.InvokeAsync<bool>("sab.openWindow", $"{page}?path={Uri.EscapeDataString(document)}", $"sab-{page}", string.Empty);
            return;
        }
        try
        {
            await Queries.NavigateAsync("tables"); // the page that asked: the home window
        }
        catch (ApiException)
        {
            // nothing to bring forward
        }
    }

    private async Task CopyAsync(string text)
    {
        await Js.InvokeAsync<bool>("sab.copy", text);
        _ = Notes.SayAsync("Copied");
    }

    private async Task NewQueryAsync(string connection)
    {
        try
        {
            await Queries.NavigateAsync($"query:{connection}");
        }
        catch (ApiException error)
        {
            _error = error;
        }
    }

    private async Task ClearAsync()
    {
        try
        {
            await Queries.ClearAsync();
            await RefreshAsync();
        }
        catch (ApiException error)
        {
            _error = error;
        }
    }

    /// <summary>The keys: the arrows move, Enter opens, Delete cancels (asked first).</summary>
    private async Task KeyAsync(KeyboardEventArgs e)
    {
        var all = Shown;
        if (all.Count == 0)
        {
            return;
        }
        var index = Math.Max(0, all.ToList().FindIndex(q => q.Id == _selected));
        switch (e.Key)
        {
            case "ArrowDown":
            case "ArrowUp":
                _selected = all[Math.Clamp(index + (e.Key == "ArrowDown" ? 1 : -1), 0, all.Count - 1)].Id;
                break;
            case "Enter":
                await ToggleAsync(all[index]);
                break;
            case "Delete":
                var q = all[index];
                if (await Dialogs.AskYesNoAsync("Cancel the query", $"Cancel {q.Who}'s {q.What} on {q.Connection}?", "Cancel it", danger: true))
                {
                    await CancelAsync(q);
                }
                break;
            default:
                break;
        }
    }

    private void OnNotice(Notice notice)
    {
        if (notice.Type == "connection_slots")
        {
            _ = InvokeAsync(RefreshAsync);
        }
    }

    public void Dispose()
    {
        Live.NoticeArrived -= OnNotice;
        _ticker?.Dispose();
    }
}
