namespace SwissArmyBench.Web.Api.Catalog;

/// <summary>A connection in the Catalog's tree: its kind, its catalog's state (loaded, loading, failed), how many
/// tables, whether its relationships can be imported, whether it needs a password here, its groups.</summary>
public sealed record BrowseConnection(
    string Name,
    string Type,
    string TablesKind,
    BrowseState State,
    bool Loaded,
    int Count,
    bool Relationships,
    bool NeedsPassword,
    IReadOnlyList<BrowseGroup> Groups);
