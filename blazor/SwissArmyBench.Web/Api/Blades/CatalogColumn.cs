namespace SwissArmyBench.Web.Api.Blades;

/// <summary>A table's column: its name, type, place and words.</summary>
public sealed record CatalogColumn(string Column, string Type = "", int Position = 0, string? Description = null);
