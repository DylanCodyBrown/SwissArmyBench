namespace SwissArmyBench.Web.Api.Settings;

/// <summary>The team this computer has joined: its repository, local copy, address on GitHub and sync words.</summary>
public sealed record TeamJoined(string Repository, string? Url = null, TeamSync? Sync = null);
