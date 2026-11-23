namespace SwissArmyBench.Web.Api.Blades;

/// <summary>A blade made or saved (its name, its new stamp and table).</summary>
public sealed record BladeMade(string Name, string? Stamp = null, string? Table = null);
