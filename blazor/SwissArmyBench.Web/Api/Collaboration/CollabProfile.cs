namespace SwissArmyBench.Web.Api.Collaboration;

/// <summary>GET /collaboration/profile: this computer's name in the panel and where it comes from (settings, github,
/// system).</summary>
public sealed record CollabProfile(string Name, string Login, string Source, string? Github = null);
