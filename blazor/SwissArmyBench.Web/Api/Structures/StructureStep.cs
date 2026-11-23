namespace SwissArmyBench.Web.Api.Structures;

/// <summary>One step on a structure (pick, filter, rename...) in plain words.</summary>
public sealed record StructureStep(string Op, string Path, string Words);
