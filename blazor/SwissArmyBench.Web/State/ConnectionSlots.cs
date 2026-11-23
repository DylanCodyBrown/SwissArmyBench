using System.Text.Json;

using SwissArmyBench.Web.Api;
using SwissArmyBench.Web.Api.Connections;

namespace SwissArmyBench.Web.State;

/// <summary>Each connection's slots now (the classic connectionSlots.ts): what runs and waits, live through the
/// connection_slots notice (never polled). A card's "Running 3 of 8 · 1 waiting" and the detail's Queries read it.</summary>
public sealed class ConnectionSlots : IDisposable
{
    private readonly QueriesClient _queries;
    private readonly LiveUpdates _live;
    private readonly Dictionary<string, SlotStatus> _statuses = new(StringComparer.OrdinalIgnoreCase);
    private Task? _loading;

    public ConnectionSlots(QueriesClient queries, LiveUpdates live)
    {
        _queries = queries;
        _live = live;
        _live.NoticeArrived += OnNotice;
    }

    public event Action? Changed;

    public Task LoadAsync() => _loading ??= RefreshAsync();

    public SlotStatus? Of(string name) => _statuses.GetValueOrDefault(name);

    /// <summary>Something runs or waits on it.</summary>
    public bool IsBusy(string name) => Of(name) is { } s && (s.Running > 0 || s.Waiting > 0);

    private async Task RefreshAsync()
    {
        try
        {
            Take(await _queries.SlotsAsync());
        }
        catch (ApiException)
        {
            // an older server: no slots
        }
    }

    private void Take(IReadOnlyList<SlotStatus> listed)
    {
        // A connection no longer named runs and waits nothing now.
        var now = listed.ToDictionary(s => s.Connection, StringComparer.OrdinalIgnoreCase);
        var idle = _statuses.Values
            .Where(s => !now.ContainsKey(s.Connection) && (s.Running > 0 || s.Waiting > 0))
            .Select(s => s with
            {
                Running = 0,
                Waiting = 0,
                AgentRunning = 0,
                AgentWaiting = 0,
                Words = $"Running 0 of {s.Limits.Total}",
                FullWords = $"Running 0 of {s.Limits.Total} · agent 0 of {s.Limits.Agent}",
            })
            .ToList();
        foreach (var s in listed.Concat(idle))
        {
            _statuses[s.Connection] = s;
        }
        Changed?.Invoke();
    }

    private void OnNotice(Notice notice)
    {
        if (notice.Type != "connection_slots")
        {
            return;
        }
        var listed = notice.Body.TryGetProperty("connections", out var connections)
            ? connections.Deserialize<List<SlotStatus>>(ApiClient.Json) ?? []
            : [];
        Take(listed);
    }

    public void Dispose() => _live.NoticeArrived -= OnNotice;
}
