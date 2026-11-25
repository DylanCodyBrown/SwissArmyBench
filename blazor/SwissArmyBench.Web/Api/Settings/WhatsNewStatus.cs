namespace SwissArmyBench.Web.Api.Settings;

/// <summary>GET /whats-new: the running version, the one last seen here, whether the window opens by itself (the first
/// start after an update), and the releases to show, newest first.</summary>
public sealed record WhatsNewStatus(string Version, string Seen, bool Open, IReadOnlyList<WhatsNewRelease> Releases);
