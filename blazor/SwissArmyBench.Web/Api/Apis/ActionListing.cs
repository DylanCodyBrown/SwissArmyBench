namespace SwissArmyBench.Web.Api.Apis;

/// <summary>GET /actions?api=: each API's actions with what was learned of them, and since when its Discover is
/// allowed.</summary>
public sealed record ActionListing(IReadOnlyList<ActionApi> Apis);
