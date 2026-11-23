namespace SwissArmyBench.Web.Api.Relationships;

/// <summary>GET /relationships: the current model's name, its tables (their primary keys), its relationships, and
/// whether its last change can be undone (and the set's description, tags and author once saved as a set).</summary>
public sealed record Model(
    IReadOnlyList<Join> Relationships,
    bool CanUndo = false,
    string Name = "current",
    IReadOnlyDictionary<string, ModelTable>? Tables = null,
    string? Description = null,
    IReadOnlyList<string>? Tags = null,
    string? Author = null);
