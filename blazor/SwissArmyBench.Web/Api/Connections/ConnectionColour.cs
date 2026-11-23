namespace SwissArmyBench.Web.Api.Connections;

/// <summary>A connection's colour (Chosen: picked by the user, else the next free one) and how each theme shows it.</summary>
public sealed record ConnectionColour(
    string Name,
    string Colour,
    IReadOnlyDictionary<string, string> Themes,
    string? Chosen = null);
