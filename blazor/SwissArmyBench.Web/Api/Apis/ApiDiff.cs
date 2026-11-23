namespace SwissArmyBench.Web.Api.Apis;

/// <summary>What changed in an API's document since it was read.</summary>
public sealed record ApiDiff(
    IReadOnlyList<ApiDiffRow> Added,
    IReadOnlyList<ApiDiffRow> Removed,
    IReadOnlyList<ApiDiffRow> Changed,
    bool Any,
    bool BaseUrl = false);
