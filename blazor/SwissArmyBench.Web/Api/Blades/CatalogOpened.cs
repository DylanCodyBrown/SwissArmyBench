namespace SwissArmyBench.Web.Api.Blades;

/// <summary>A catalog's table opened as a grid: its dataset, and how many rows of how many.</summary>
public sealed record CatalogOpened(string Dataset, int? Shown = null, long? Total = null);
