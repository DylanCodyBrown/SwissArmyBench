namespace SwissArmyBench.Web.Api.Collaboration;

/// <summary>
/// One thread of the timeline: its title, where it is, its first message, replies, unread, resolved and pinned; with
/// its messages when it is opened. Only what people write (the owner, 2026-11-25: the change log stays out).
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
    IReadOnlyList<CollabMessage>? Messages = null)
{
    /// <summary>When it last moved: its last message.</summary>
    public string When => Last ?? Created ?? string.Empty;
}
