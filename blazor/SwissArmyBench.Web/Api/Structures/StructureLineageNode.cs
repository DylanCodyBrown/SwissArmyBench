namespace SwissArmyBench.Web.Api.Structures;

/// <summary>One step of a structure's lineage: what, its words and where.</summary>
public sealed record StructureLineageNode(string Kind, string Label, string Where = "");
