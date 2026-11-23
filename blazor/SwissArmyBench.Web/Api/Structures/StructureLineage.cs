using System.Text.Json;

namespace SwissArmyBench.Web.Api.Structures;

/// <summary>GET /structures/{id}/lineage: the diagram (Mermaid), its nodes and where it came from.</summary>
public sealed record StructureLineage(string Mermaid, IReadOnlyList<StructureLineageNode> Nodes, JsonElement Origin);
