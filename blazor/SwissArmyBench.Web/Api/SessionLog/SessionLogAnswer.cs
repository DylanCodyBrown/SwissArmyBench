namespace SwissArmyBench.Web.Api.SessionLog;

/// <summary>GET /session-log: this session's entries, newest first, and Follow the agent.</summary>
public sealed record SessionLogAnswer(IReadOnlyList<SessionEntry> Entries, string Who, bool Follow, SessionCounts Counts);
