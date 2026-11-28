namespace SwissArmyBench.Web.Api.Extensions;

/// <summary>GET /extensions: every card the server lists.</summary>
public sealed record ExtensionListing(IReadOnlyList<ExtensionInfo> Extensions);
