namespace SwissArmyBench.Web.Api.Analyze;

/// <summary>A theme the Analyze board can take (domain/themes.py): its name, light or dark, its group and note,
/// whether the user imported it or the agent made it, its colour tokens and its categorical colours.</summary>
public sealed record BoardTheme(
    string Id,
    string Label,
    bool Dark,
    string Group,
    string Note,
    bool Custom,
    bool ByAgent,
    IReadOnlyDictionary<string, string> Tokens,
    IReadOnlyList<string> Cat);
