namespace SwissArmyBench.Web.Api.Extensions;

/// <summary>POST /extensions/remove: asked first (its question), or the folder gone at once.</summary>
public sealed record ExtensionChange(string? Confirm = null, string? Removed = null);
