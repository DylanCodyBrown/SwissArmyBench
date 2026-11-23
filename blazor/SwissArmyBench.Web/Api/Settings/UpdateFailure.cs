namespace SwissArmyBench.Web.Api.Settings;

/// <summary>The last update that failed (read once): its version and why.</summary>
public sealed record UpdateFailure(string Version, string Reason = "");
