namespace SwissArmyBench.Web.Api.Files;

/// <summary>GET /dialogs: whether this computer's own file dialog opens, and why not.</summary>
public sealed record DialogsStatus(bool System, string? Tool = null, string? Reason = null);
