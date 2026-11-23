namespace SwissArmyBench.Web.Api.LocalApi;

/// <summary>GET /local-api/shapes: each canvas widget that uses an endpoint, what it expects beside what the endpoint answers.</summary>
public sealed record PayloadShapes(IReadOnlyList<PayloadUse> Uses);
