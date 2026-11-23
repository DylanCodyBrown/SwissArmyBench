namespace SwissArmyBench.Web.Api.Settings;

/// <summary>GET /updates: this version, the latest, and whether an update is available.</summary>
public sealed record UpdatesStatus(string Current, string? Latest, bool Available, string? Version = null, string? Url = null, string Name = "Swiss Army Bench");
