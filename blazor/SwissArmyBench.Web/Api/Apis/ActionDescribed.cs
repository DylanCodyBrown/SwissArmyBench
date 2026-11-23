namespace SwissArmyBench.Web.Api.Apis;

/// <summary>GET /actions/{api}/{action}: the action's contract.</summary>
public sealed record ActionDescribed(ActionContract Contract);
