using System.Globalization;
using System.Text.Json;

using Microsoft.AspNetCore.Components;
using Microsoft.JSInterop;

using SwissArmyBench.Web.Api;
using SwissArmyBench.Web.Api.SessionLog;
using SwissArmyBench.Web.State;

namespace SwissArmyBench.Web.Pages.Session;

public partial class SessionPage : IDisposable
{
    private readonly (string Value, string Label)[] _whose = [("agent", "The agent"), ("user", "Me"), ("both", "Both")];

    private List<SessionEntry>? _entries;
    private Exception? _error;
    private string _who = "agent";
    private bool _changesOnly;
    private bool _follow = true;

    [Inject]
    private SessionLogClient SessionLog { get; set; } = default!;

    [Inject]
    private LiveUpdates Live { get; set; } = default!;

    [Inject]
    private RailState RailState { get; set; } = default!;

    [Inject]
    private IJSRuntime Js { get; set; } = default!;

    protected override async Task OnInitializedAsync()
    {
        await Js.InvokeVoidAsync("sab.setTitle", "Session");
        _who = await Js.InvokeAsync<string?>("sab.recall", "sessionWho") ?? "agent";
        Live.NoticeArrived += OnNotice;
        RailState.SessionSeen();
        await LoadAsync();
    }

    private async Task LoadAsync()
    {
        try
        {
            var answer = await SessionLog.ListingAsync(_who, _changesOnly);
            _entries = [.. answer.Entries];
            _follow = answer.Follow;
            _error = null;
        }
        catch (ApiException error)
        {
            _error = error;
            _entries ??= [];
        }
    }

    private async Task WhoAsync(string who)
    {
        _who = who;
        await Js.InvokeVoidAsync("sab.remember", "sessionWho", who);
        await LoadAsync();
    }

    private Task ChangesAsync(ChangeEventArgs e)
    {
        _changesOnly = e.Value is true;
        return LoadAsync();
    }

    private async Task FollowAsync(ChangeEventArgs e)
    {
        try
        {
            _follow = (await SessionLog.SetFollowAsync(e.Value is true)).Follow;
        }
        catch (ApiException error)
        {
            _error = error;
        }
    }

    /// <summary>The time of day an entry was made, in this computer's own time.</summary>
    private static string TimeOf(string time) =>
        DateTimeOffset.TryParse(time, CultureInfo.InvariantCulture, DateTimeStyles.None, out var when) ? when.ToLocalTime().ToString("HH:mm:ss") : time;

    /// <summary>Where an entry's link goes in this front end: its area's page, with the object named.</summary>
    private static string? LinkOf(SessionEntry entry) => entry.Area switch
    {
        "grids" when entry.Target?.Grid is { } grid => $"grids?grid={Uri.EscapeDataString(grid)}",
        "grids" when entry.Target?.Dataset is { } dataset => $"grids?table={Uri.EscapeDataString(dataset)}",
        "connections" when entry.Target?.Connection is { } name => $"connections?name={Uri.EscapeDataString(name)}",
        "grids" or "connections" or "analyze" or "erd" or "environment" or "apis" or "notebooks" or "scripts" => entry.Area,
        _ => null,
    };

    private void OnNotice(Notice notice)
    {
        if (notice.Type == "session_follow")
        {
            _follow = notice.Flag("follow") ?? _follow;
        }
        else if (notice.Type == "session_entry" && notice.Body.TryGetProperty("entry", out var raw))
        {
            var entry = raw.Deserialize<SessionEntry>(ApiClient.Json);
            if (entry is null || _entries is null || _entries.Any(e => e.Id == entry.Id) || !Wanted(entry))
            {
                return;
            }
            _entries.Insert(0, entry);
            RailState.SessionSeen();
        }
        _ = InvokeAsync(StateHasChanged);
    }

    private bool Wanted(SessionEntry entry) =>
        (_who == "both" || entry.Actor == _who) && (!_changesOnly || entry.Change is not null);

    public void Dispose()
    {
        Live.NoticeArrived -= OnNotice;
        GC.SuppressFinalize(this);
    }

    /// <summary>The empty log's Launch Claude: the footer's own button does the launch (one way to launch).</summary>
    private Task LaunchClaudeAsync() => Js.InvokeVoidAsync("sab.click", ".status-bar .claude-launch").AsTask();
}
