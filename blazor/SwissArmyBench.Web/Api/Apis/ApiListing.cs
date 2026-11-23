namespace SwissArmyBench.Web.Api.Apis;

/// <summary>GET /apis, as the cards read it: the library's APIs and the older API connections.</summary>
public sealed record ApiListing(IReadOnlyList<ApiCardInfo> Apis, IReadOnlyList<OlderApi> Older);
