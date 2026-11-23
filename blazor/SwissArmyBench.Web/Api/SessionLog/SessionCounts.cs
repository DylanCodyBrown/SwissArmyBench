namespace SwissArmyBench.Web.Api.SessionLog;

/// <summary>How many entries each side made this session.</summary>
public sealed record SessionCounts(int Agent = 0, int User = 0);
