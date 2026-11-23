namespace SwissArmyBench.Web.Api.Extensions;

/// <summary>POST /extensions/install or /remove: asked first, under way (the app restarts), or a folder's gone at once.</summary>
public sealed record ExtensionChange(
    string? Confirm = null,
    ChangingExtension? Changing = null,
    string? Removed = null);
