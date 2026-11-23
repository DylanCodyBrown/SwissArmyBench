namespace SwissArmyBench.Web.Api.Environment;

/// <summary>Where a use goes: a grid, a document's cell, a connection, a table, an area.</summary>
public sealed record EnvironmentUseLink(
    string? To = null,
    string? Grid = null,
    string? Path = null,
    int? Cell = null,
    string? Name = null);
