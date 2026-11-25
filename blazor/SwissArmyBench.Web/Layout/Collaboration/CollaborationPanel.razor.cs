using Microsoft.AspNetCore.Components;
using Microsoft.JSInterop;

using SwissArmyBench.Web.Api;
using SwissArmyBench.Web.Api.Collaboration;
using SwissArmyBench.Web.Api.Projects;
using SwissArmyBench.Web.Api.Settings;
using SwissArmyBench.Web.State;

namespace SwissArmyBench.Web.Layout.Collaboration;

public partial class CollaborationPanel
{
    private const string AllFilter = "all";

    private ElementReference _panel;
    private ElementReference _handle;
    private ElementReference _edge;
    private IJSObjectReference? _module;
    private IJSObjectReference? _placed;
    private CollabTimeline? _timeline;
    private CollabItem? _thread;
    private CollabSearch? _found;
    private Exception? _error;
    private string _filter = AllFilter;
    private string _words = string.Empty;
    private int _seenVersion = -1;
    private bool _scrollDown = true;
    private string? _shownKey;
    private string? _seenWhere;
    private string? _seenPage;
    private DateTimeOffset _now = DateTimeOffset.UtcNow;

    [Inject]
    private IJSRuntime Js { get; set; } = default!;

    [Inject]
    private CollaborationClient Client { get; set; } = default!;

    [Inject]
    private CollaborationState State { get; set; } = default!;

    [Inject]
    private SettingsClient Settings { get; set; } = default!;

    [Inject]
    private ProjectsClient Projects { get; set; } = default!;

    [Inject]
    private ProjectState Project { get; set; } = default!;

    [Inject]
    private Dialogs Dialogs { get; set; } = default!;

    /// <summary>The kind of window (its place is kept per kind).</summary>
    [Parameter, EditorRequired]
    public string Kind { get; set; } = string.Empty;

    [Parameter]
    public EventCallback OnClose { get; set; }

    private string PostPlaceholder => State.Anchor is { } anchor
        ? $"A note on {anchor.Text}"
        : State.Where is { Length: > 0 } where ? $"A note in {where}" : "A note in #general";

    protected override async Task OnInitializedAsync()
    {
        State.Changed += OnState;
        await LoadAsync();
    }

    protected override async Task OnAfterRenderAsync(bool firstRender)
    {
        if (firstRender)
        {
            _module = await Js.InvokeAsync<IJSObjectReference>("import", "./js/collaboration.js");
            _placed = await _module.InvokeAsync<IJSObjectReference>("place", _panel, _handle, _edge, Kind);
        }
        if (_module is not null)
        {
            await _module.InvokeVoidAsync("highlight", _panel);
            if (_scrollDown)
            {
                _scrollDown = false;
                await _module.InvokeVoidAsync("scrollEnd", _panel);
            }
        }
    }

    private static string Unread(int count) => count > 0 ? $" ({count})" : string.Empty;

    /// <summary>The timeline read again, and the thread open (a notice, a filter, a place).</summary>
    private async Task LoadAsync()
    {
        _seenVersion = State.Version;
        _seenWhere = State.Where;
        _seenPage = State.Page;
        _now = DateTimeOffset.UtcNow;
        try
        {
            var count = _timeline?.Items.Count;
            _timeline = await Client.TimelineAsync(State.Where, _filter, State.Page);
            _scrollDown |= count != _timeline.Items.Count;
            if (_timeline.Unread is { } counts)
            {
                State.TakeCounts(counts);
            }
            if (State.OpenThread is { } asked)
            {
                State.TookThread();
                await OpenAsync(asked);
            }
            else if (_thread is { } open)
            {
                await ShowThreadAsync(await Client.ThreadAsync(open.Id));
            }
            if (!string.IsNullOrWhiteSpace(_words))
            {
                _found = await Client.SearchAsync(_words);
            }
        }
        catch (ApiException error)
        {
            _error = error;
        }
    }

    private void OnState()
    {
        if (State.Version != _seenVersion || State.Where != _seenWhere || State.Page != _seenPage || State.OpenThread is not null)
        {
            if (State.Where != _seenWhere)
            {
                _thread = null;
            }
            _ = InvokeAsync(async () =>
            {
                await LoadAsync();
                StateHasChanged();
            });
        }
    }

    private async Task OpenAsync(string thread)
    {
        try
        {
            await ShowThreadAsync(await Client.ThreadAsync(thread));
        }
        catch (ApiException error)
        {
            _error = error;
        }
    }

    /// <summary>A thread shown: read up to its last message (this computer's marks, the status bar's count).</summary>
    private async Task ShowThreadAsync(CollabItem thread)
    {
        var key = $"{thread.Id}:{thread.Messages?.Count}";
        _scrollDown |= key != _shownKey;
        _shownKey = key;
        _thread = thread;
        if (thread.Unread > 0)
        {
            State.TakeCounts(await Client.ReadAsync(thread.Id));
        }
    }

    private Task BackAsync()
    {
        _thread = null;
        _shownKey = null;
        _scrollDown = true;
        return LoadAsync();
    }

    private void TookThread(CollabItem thread) => _thread = thread;

    private void Failed(Exception error) => _error = error;

    private async Task GoAsync(ChangeEventArgs e)
    {
        State.Go(e.Value?.ToString());
        await LoadAsync();
    }

    private Task FilterAsync(string filter)
    {
        _filter = filter;
        return LoadAsync();
    }

    private async Task SearchAsync()
    {
        try
        {
            _found = string.IsNullOrWhiteSpace(_words) ? null : await Client.SearchAsync(_words);
        }
        catch (ApiException error)
        {
            _error = error;
        }
    }

    private Task<bool> PostAsync(string body, IReadOnlyList<CollabImage> images) => SentAsync(async () =>
    {
        var channel = State.Anchor is null ? State.Where?.TrimStart('#') : null;
        var made = await Client.PostAsync(string.IsNullOrEmpty(channel) ? null : channel, State.Anchor, body, images);
        await LoadAsync();
        return made;
    });

    private Task<bool> ReplyAsync(string body, IReadOnlyList<CollabImage> images) =>
        SentAsync(() => Client.ReplyAsync(_thread!.Id, body, images), show: true);

    private async Task<bool> SentAsync(Func<Task<CollabItem>> send, bool show = false)
    {
        try
        {
            var thread = await send();
            if (show)
            {
                await ShowThreadAsync(thread);
            }
            _scrollDown = true;
            StateHasChanged();
            return true;
        }
        catch (ApiException error)
        {
            _error = error;
            StateHasChanged();
            return false;
        }
    }

    private Task ResolveAsync(bool resolved) => SentAsync(() => Client.ResolveAsync(_thread!.Id, resolved), show: true);

    private Task PinAsync(bool pinned) => SentAsync(() => Client.PinAsync(_thread!.Id, pinned), show: true);

    private async Task NewChannelAsync()
    {
        var name = await Dialogs.AskTextAsync("New channel", "A channel the team can post in, such as #month-end.", "Name", string.Empty, "Make it");
        if (string.IsNullOrWhiteSpace(name))
        {
            return;
        }
        try
        {
            var made = await Client.ChannelAsync(name);
            State.Go(made.Key);
            await LoadAsync();
        }
        catch (ApiException error)
        {
            _error = error;
        }
    }

    private async Task ShareAsync()
    {
        if (Project.Current is not { } open
            || !await Dialogs.AskYesNoAsync("Share this project?", $"{open.Name} is copied into the team's shared projects folder and opened there; its notes go with it when you push.", "Share"))
        {
            return;
        }
        await TeamAsync(async () =>
        {
            await Projects.ShareAsync(open.Path);
            await Project.RefreshAsync();
        });
    }

    private Task PullAsync() => TeamAsync(Settings.TeamPullAsync);

    private Task PushAsync() => TeamAsync(Settings.TeamPushAsync);

    private async Task TeamAsync(Func<Task> act)
    {
        try
        {
            await act();
            await LoadAsync();
        }
        catch (ApiException error)
        {
            _error = error;
        }
    }

    public async ValueTask DisposeAsync()
    {
        State.Changed -= OnState;
        if (_placed is not null)
        {
            await _placed.InvokeVoidAsync("stop");
            await _placed.DisposeAsync();
        }
        if (_module is not null)
        {
            await _module.DisposeAsync();
        }
        GC.SuppressFinalize(this);
    }
}
