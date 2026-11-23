namespace SwissArmyBench.Web.Api.Workbench;

/// <summary>One of a structure's steps (Pick, Filter, Sort, Flatten) in words.</summary>
public sealed record StructureStep(string Op, string Path, string Words);
