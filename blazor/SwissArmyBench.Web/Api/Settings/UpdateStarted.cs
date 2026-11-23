namespace SwissArmyBench.Web.Api.Settings;

/// <summary>POST /updates/install: under way, or what it would lose first.</summary>
public sealed record UpdateStarted(UpdateRisk? Confirm = null, string? Updating = null);
