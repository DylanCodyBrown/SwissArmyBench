namespace SwissArmyBench.Web.Api.Collaboration;

/// <summary>
/// The Collaboration panel's routes (server/routes_collaboration.py): the timeline, a thread, posting, replying,
/// editing and deleting your own, reactions, resolve, pin, channels, the read marks, search, the `@` picker, a pasted
/// picture's address and this computer's name. Every write answers the thread as it is now.
/// </summary>
public sealed class CollaborationClient
{
    private readonly ApiClient _api;

    public CollaborationClient(ApiClient api)
    {
        _api = api;
    }

    public Task<CollabTimeline> TimelineAsync(string? where, string filter, string? page)
    {
        var query = new List<string> { $"filter={ApiClient.Part(filter)}" };
        if (!string.IsNullOrEmpty(where))
        {
            query.Add($"where={ApiClient.Part(where)}");
        }
        if (!string.IsNullOrEmpty(page))
        {
            query.Add($"page={ApiClient.Part(page)}");
        }
        return _api.GetAsync<CollabTimeline>($"/collaboration?{string.Join('&', query)}");
    }

    public Task<CollabItem> ThreadAsync(string id) => _api.GetAsync<CollabItem>($"/collaboration/thread?id={ApiClient.Part(id)}");

    /// <summary>A new thread in a channel, or on an object (its anchor).</summary>
    public Task<CollabItem> PostAsync(string? channel, CollabReference? anchor, string body, IReadOnlyList<CollabImage> images) =>
        _api.PostAsync<CollabItem>("/collaboration/post", new
        {
            channel,
            anchor = anchor is null ? null : new { anchor.Kind, anchor.Path, anchor.Id, anchor.Text },
            body,
            images,
        });

    public Task<CollabItem> ReplyAsync(string thread, string body, IReadOnlyList<CollabImage> images) =>
        _api.PostAsync<CollabItem>("/collaboration/reply", new { thread, body, images });

    public Task<CollabItem> EditAsync(string thread, string message, string body) =>
        _api.PostAsync<CollabItem>("/collaboration/edit", new { thread, message, body });

    public Task<CollabItem> DeleteAsync(string thread, string message) =>
        _api.PostAsync<CollabItem>("/collaboration/delete", new { thread, message });

    public Task<CollabItem> ReactAsync(string thread, string message, string emoji) =>
        _api.PostAsync<CollabItem>("/collaboration/react", new { thread, message, emoji });

    public Task<CollabItem> ResolveAsync(string thread, bool resolved) =>
        _api.PostAsync<CollabItem>("/collaboration/resolve", new { thread, resolved });

    public Task<CollabItem> PinAsync(string thread, bool pinned) =>
        _api.PostAsync<CollabItem>("/collaboration/pin", new { thread, pinned });

    public Task<CollabChannel> ChannelAsync(string name) => _api.PostAsync<CollabChannel>("/collaboration/channel", new { name });

    /// <summary>The panel showed a thread: read up to its last message (this computer's marks).</summary>
    public Task<CollabUnread> ReadAsync(string thread) => _api.PostAsync<CollabUnread>("/collaboration/read", new { thread });

    public Task<CollabUnread> UnreadAsync() => _api.GetAsync<CollabUnread>("/collaboration/unread");

    public Task<CollabSearch> SearchAsync(string words) => _api.GetAsync<CollabSearch>($"/collaboration/search?words={ApiClient.Part(words)}");

    public Task<CollabPicks> ObjectsAsync(string words, string? page) =>
        _api.GetAsync<CollabPicks>($"/collaboration/objects?words={ApiClient.Part(words)}" + (page is null ? string.Empty : $"&page={ApiClient.Part(page)}"));

    public Task<CollabProfile> ProfileAsync() => _api.GetAsync<CollabProfile>("/collaboration/profile");

    public Task<CollabProfile> SetProfileAsync(string name) => _api.PutAsync<CollabProfile>("/collaboration/profile", new { name });

    /// <summary>A pasted picture's address (the page's cookie rides on it).</summary>
    public static string ImageAddress(string thread, string name) =>
        $"/collaboration/image?thread={ApiClient.Part(thread)}&name={ApiClient.Part(name)}";
}
