namespace SwissArmyBench.Web.Api.App;

/// <summary>GET /app/modes: every project type this app can make, each with its mode.</summary>
public sealed record ModesAnswer(IReadOnlyList<ModeInfo> Modes);
