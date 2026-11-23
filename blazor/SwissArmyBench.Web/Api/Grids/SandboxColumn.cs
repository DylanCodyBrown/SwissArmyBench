namespace SwissArmyBench.Web.Api.Grids;

/// <summary>A sandbox table's column: its name, its DuckDB type, whether it is part of the key.</summary>
public sealed record SandboxColumn(string Name, string Type, bool Key = false);
