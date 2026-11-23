namespace SwissArmyBench.Web.Api.LocalApi;

/// <summary>GET /local-api/log: the requests and what the process printed.</summary>
public sealed record LocalApiLog(IReadOnlyList<LocalApiRequest> Log, IReadOnlyList<string>? Output = null);
