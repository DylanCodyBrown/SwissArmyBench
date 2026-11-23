using System.Text.Json;

namespace SwissArmyBench.Web.Components;

/// <summary>A node of a structure's tree right-clicked: its path and value, its place in its list (Move up and down)
/// and where the pointer was.</summary>
public sealed record StructureNodeMenu(string Path, JsonElement Value, int? Index, int Siblings, double X, double Y);
