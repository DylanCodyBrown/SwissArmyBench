namespace SwissArmyBench.Web.Api.Grids;

/// <summary>The work sent to a source with a read: its filters in words.</summary>
public sealed record SentWork(string? Filters = null);
