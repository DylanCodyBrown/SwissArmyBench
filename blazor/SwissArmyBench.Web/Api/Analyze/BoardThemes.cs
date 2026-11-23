namespace SwissArmyBench.Web.Api.Analyze;

/// <summary>GET /analyze/themes: the board's current theme (an id, or "app": it follows the app) and every theme.</summary>
public sealed record BoardThemes(string Current, IReadOnlyList<BoardTheme> Themes);
