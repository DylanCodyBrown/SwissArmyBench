namespace SwissArmyBench.Web.Api.Settings;

/// <summary>GET /updates: this version, the latest, whether an update is available, one under way, the last one failed.</summary>
public sealed record UpdatesStatus(
    string Current,
    string? Latest,
    bool Available,
    string? Version = null,
    string? Url = null,
    string Name = "Swiss Army Bench",
    string? Updating = null,
    UpdateFailure? Failed = null);
