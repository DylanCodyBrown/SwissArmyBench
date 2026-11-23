namespace SwissArmyBench.Web.Api.Sandbox;

/// <summary>A sandbox table's column: its name, type and whether it is part of the key.</summary>
public sealed record SandboxColumn(string Name, string Type, bool Key = false);
