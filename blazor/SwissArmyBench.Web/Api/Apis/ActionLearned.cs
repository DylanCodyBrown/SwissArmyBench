namespace SwissArmyBench.Web.Api.Apis;

/// <summary>What was learned of one action: its kind, whether it was seen, its drift.</summary>
public sealed record ActionLearned(
    string Name,
    string Kind = "",
    bool Learned = false,
    string Drift = "");
