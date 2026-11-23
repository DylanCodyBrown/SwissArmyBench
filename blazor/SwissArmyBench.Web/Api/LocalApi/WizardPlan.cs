namespace SwissArmyBench.Web.Api.LocalApi;

/// <summary>POST /local-api/plan: New endpoint's sandbox tables, the patterns ranked by the table's shape, the picked one's steps and fields, the code it adds or the one thing missing.</summary>
public sealed record WizardPlan(
    IReadOnlyList<WizardTable> Tables,
    string? Table = null,
    IReadOnlyList<WizardRanked>? Ranked = null,
    WizardPatternPlan? Plan = null,
    IReadOnlyList<string>? Others = null,
    string? Problem = null,
    string? Code = null,
    string? Imports = null,
    IReadOnlyList<string>? Added = null,
    string? Words = null);
