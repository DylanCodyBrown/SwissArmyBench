namespace SwissArmyBench.Web.Api.Apis;

/// <summary>GET /apis/search: the results.</summary>
public sealed record ApiHits(IReadOnlyList<ApiHit> Results);
