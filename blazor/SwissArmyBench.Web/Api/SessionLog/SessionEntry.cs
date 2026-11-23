namespace SwissArmyBench.Web.Api.SessionLog;

/// <summary>One entry of the Session page's log: who did what, its area and its object.</summary>
public sealed record SessionEntry(int Id, string Time, string Actor, string Action, string What, string? Area = null, SessionTarget? Target = null, string? Change = null);
