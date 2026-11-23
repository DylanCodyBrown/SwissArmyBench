namespace SwissArmyBench.Web.Api.LocalApi;

/// <summary>One pattern ranked for the table: whether it fits, and one sentence why.</summary>
public sealed record WizardRanked(
    string Pattern,
    string Label,
    string Question,
    bool Fits,
    string Why);
