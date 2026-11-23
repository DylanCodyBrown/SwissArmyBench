namespace SwissArmyBench.Web.Api.Environment;

/// <summary>POST /environment/clear {dry_run}: what each tick would clear, and its words.</summary>
public sealed record ClearChoices(
    IReadOnlyDictionary<string, IReadOnlyList<string>> Would,
    IReadOnlyDictionary<string, string> Choices);
