namespace SwissArmyBench.Web.Api.Connections;

/// <summary>GET /connection-colours: every connection's colour and the palette.</summary>
public sealed record ColourListing(IReadOnlyList<ConnectionColour> Connections, IReadOnlyList<PaletteColour> Palette);
