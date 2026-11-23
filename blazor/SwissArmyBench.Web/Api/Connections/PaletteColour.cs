namespace SwissArmyBench.Web.Api.Connections;

/// <summary>One colour of the palette and how each theme shows it.</summary>
public sealed record PaletteColour(string Name, string Colour, IReadOnlyDictionary<string, string> Themes);
