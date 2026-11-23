namespace SwissArmyBench.Web.Api.Grids;

/// <summary>GET /grids/{id}/step-counts: the rows entering each step, then the view's.</summary>
public sealed record StepCounts(IReadOnlyList<long> Counts);
