namespace SwissArmyBench.Web.Api.Collaboration;

/// <summary>GET /collaboration/objects: what `@` offers (the people who wrote here, the project's objects, each with
/// its link).</summary>
public sealed record CollabPicks(IReadOnlyList<CollabPerson> People, IReadOnlyList<CollabReference> Objects);
