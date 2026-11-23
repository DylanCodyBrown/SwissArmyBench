namespace SwissArmyBench.Web.Api.Settings;

/// <summary>GET /agent/approvals: the requests waiting.</summary>
public sealed record Approvals(IReadOnlyList<Approval> Pending);
