namespace SwissArmyBench.Web.Api.Environment;

/// <summary>Where an opened row lands: to a grid (its id), a structure, a page.</summary>
public sealed record EnvironmentLink(string To, string? Grid);
