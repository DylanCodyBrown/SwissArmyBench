namespace SwissArmyBench.Web.Api.Environment;

/// <summary>One place a row is used (a grid, a cell, a canvas widget, an endpoint), in words.</summary>
public sealed record EnvironmentUse(string Kind, string Words);
