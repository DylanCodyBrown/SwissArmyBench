namespace SwissArmyBench.Web.Api.Collaboration;

/// <summary>
/// One line of the timeline: a thread (its title, where it is, its first message, replies, unread, resolved, pinned;
/// with its messages when it is opened) or an activity line (a person's change in words, the threads replying to it).
/// </summary>
public sealed record CollabItem(
    string Type,
    string Id,
    string? Title = null,
    string? Where = null,
    CollabReference? Anchor = null,
    CollabPerson? CreatedBy = null,
    string? Created = null,
    CollabResolved? Resolved = null,
    bool Pinned = false,
    int Replies = 0,
    string? Last = null,
    int Unread = 0,
    CollabMessage? First = null,
    IReadOnlyList<CollabMessage>? Messages = null,
    string? Time = null,
    CollabPerson? Author = null,
    CollabChange? Object = null,
    string? Words = null,
    IReadOnlyList<string>? Threads = null)
{
    public const string ThreadType = "thread";
    public const string ActivityType = "activity";

    public bool IsThread => Type == ThreadType;

    /// <summary>When it happened: a thread's last message, an activity line's time.</summary>
    public string When => (IsThread ? Last ?? Created : Time) ?? string.Empty;
}
