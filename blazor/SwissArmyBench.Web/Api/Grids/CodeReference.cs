namespace SwissArmyBench.Web.Api.Grids;

/// <summary>A cell or a script line that names a connection: its document, title, kind, the line, its cell number and
/// name, and whether it can be pointed at another connection here.</summary>
public sealed record CodeReference(
    string Document,
    string Title,
    string Kind,
    string Line,
    int? Cell = null,
    string? Name = null,
    bool Pickable = false);
