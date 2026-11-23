namespace SwissArmyBench.Web.Api.Settings;

/// <summary>POST /team/join or /team/start: the repository joined or made.</summary>
public sealed record TeamMade(string? Joined = null, string? Started = null);
