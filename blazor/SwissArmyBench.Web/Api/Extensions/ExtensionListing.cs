namespace SwissArmyBench.Web.Api.Extensions;

/// <summary>GET /extensions: every card, whether this copy can install, one being changed.</summary>
public sealed record ExtensionListing(
    IReadOnlyList<ExtensionInfo> Extensions,
    bool Installable = false,
    ChangingExtension? Changing = null);
