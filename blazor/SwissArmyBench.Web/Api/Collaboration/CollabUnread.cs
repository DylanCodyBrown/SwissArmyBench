namespace SwissArmyBench.Web.Api.Collaboration;

/// <summary>The unread counts: every thread's, the mentions of you, and each channel's and object's by its key.</summary>
public sealed record CollabUnread(int Total, int Mentions, IReadOnlyDictionary<string, int>? Places = null);
