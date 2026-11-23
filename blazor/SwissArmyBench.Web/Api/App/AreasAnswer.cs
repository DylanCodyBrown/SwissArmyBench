namespace SwissArmyBench.Web.Api.App;

/// <summary>GET /app/areas.</summary>
public sealed record AreasAnswer(IReadOnlyList<AreaInfo> Areas);
