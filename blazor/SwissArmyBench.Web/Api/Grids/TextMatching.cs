namespace SwissArmyBench.Web.Api.Grids;

/// <summary>How a table's filters, categorize rules and exported code compare text (the classic textMatching.ts).</summary>
public sealed record TextMatching(
    bool CaseSensitive,
    bool Wildcards,
    bool TrimSpaces,
    bool EmptyIsBlank);
