namespace SwissArmyBench.Web.Api.Grids;

/// <summary>A document that could not be pointed at another connection, and why.</summary>
public sealed record RepointFailure(string Document, string Error);
