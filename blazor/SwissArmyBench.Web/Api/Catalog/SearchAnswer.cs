namespace SwissArmyBench.Web.Api.Catalog;

/// <summary>GET /explorer/search?q=: everything that holds data, matched in any case and by parts, grouped by kind.</summary>
public sealed record SearchAnswer(IReadOnlyList<SearchGroup> Groups);
