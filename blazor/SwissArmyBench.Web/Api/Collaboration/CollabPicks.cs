namespace SwissArmyBench.Web.Api.Collaboration;

/// <summary>GET /collaboration/objects: what `@` offers, in its order: the page's objects, the people who wrote here
/// (and you), the rest of the project's objects; each object with its link.</summary>
public sealed record CollabPicks(
    IReadOnlyList<CollabPerson> People,
    IReadOnlyList<CollabReference> Objects,
    IReadOnlyList<CollabReference>? Page = null);
