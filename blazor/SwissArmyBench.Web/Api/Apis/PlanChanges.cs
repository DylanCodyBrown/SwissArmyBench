namespace SwissArmyBench.Web.Api.Apis;

/// <summary>What a re-import changes.</summary>
public sealed record PlanChanges(
    IReadOnlyList<string> Added,
    IReadOnlyList<string> Removed,
    IReadOnlyList<string> Changed,
    bool Auth,
    bool BaseUrl,
    bool Any);
