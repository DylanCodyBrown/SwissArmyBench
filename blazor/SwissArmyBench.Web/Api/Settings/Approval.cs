namespace SwissArmyBench.Web.Api.Settings;

/// <summary>A request of the agent's waiting for the user's Allow: what it wants to do, on what, in detail.</summary>
public sealed record Approval(string Id, string Dataset = "", string Action = "", string Detail = "");
