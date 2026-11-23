namespace SwissArmyBench.Web.Api.App;

/// <summary>GET /app/mode: the open project's type and its mode.</summary>
public sealed record ModeAnswer(string? Project, string ProjectType, ModeInfo Mode);
