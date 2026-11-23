namespace SwissArmyBench.Web.Api.Structures;

/// <summary>GET /structures, as the Structures page reads it: the open structures (its tabs) and the project's files.</summary>
public sealed record StructureTabs(IReadOnlyList<StructureShown> Open, IReadOnlyList<StructureFile> Files);
