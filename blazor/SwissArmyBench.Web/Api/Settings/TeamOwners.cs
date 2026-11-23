namespace SwissArmyBench.Web.Api.Settings;

/// <summary>GET /team/owners: who can own a new team's repository.</summary>
public sealed record TeamOwners(IReadOnlyList<string> Owners);
