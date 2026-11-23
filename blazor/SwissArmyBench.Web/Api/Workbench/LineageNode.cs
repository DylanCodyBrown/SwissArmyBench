namespace SwissArmyBench.Web.Api.Workbench;

/// <summary>One step of a lineage: a cell, a table, a grid step or a source; where it is, and its cell.</summary>
public sealed record LineageNode(
    string Id,
    string Kind,
    string Label,
    string Where,
    string? Document,
    int? Cell,
    string? DocKind,
    bool Target);
