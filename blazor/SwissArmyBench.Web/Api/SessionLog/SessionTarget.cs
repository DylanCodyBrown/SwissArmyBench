namespace SwissArmyBench.Web.Api.SessionLog;

/// <summary>What a Session entry names, so its link goes there (a grid, a card, a connection, a cell).</summary>
public sealed record SessionTarget(string Place, string? Dataset = null, string? Grid = null, string? Connection = null, string? Path = null, string? Card = null);
