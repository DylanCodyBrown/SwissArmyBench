namespace SwissArmyBench.Web.Api.Environment;

/// <summary>One place a row is used (a grid, a cell, a canvas widget, an endpoint), in words, and where it goes.</summary>
public sealed record EnvironmentUse(string Kind, string Words, EnvironmentUseLink? Link = null);
