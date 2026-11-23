namespace SwissArmyBench.Web.Api.LocalApi;

/// <summary>POST /local-api/check: each endpoint's SQL checked.</summary>
public sealed record RealChecks(IReadOnlyList<RealCheck> Checks);
