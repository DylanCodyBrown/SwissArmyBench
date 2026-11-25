namespace SwissArmyBench.Web.Api.Collaboration;

/// <summary>GET /collaboration: the open project (null: none), you, whether the project is shared with the team and
/// the team's word, the channels, the objects with threads, the people, the timeline's lines and the unread counts.</summary>
public sealed record CollabTimeline(
    string? Project,
    CollabPerson Me,
    IReadOnlyList<CollabItem> Items,
    IReadOnlyList<CollabChannel> Channels,
    IReadOnlyList<CollabReference> Objects,
    bool Shared = false,
    CollabTeam? Team = null,
    IReadOnlyList<CollabPerson>? People = null,
    CollabUnread? Unread = null);
