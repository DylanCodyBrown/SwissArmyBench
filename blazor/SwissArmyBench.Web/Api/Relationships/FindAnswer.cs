namespace SwissArmyBench.Web.Api.Relationships;

/// <summary>POST /relationships/find: the finder's suggestions among the tables named, each table's key, and how long
/// it took.</summary>
public sealed record FindAnswer(
    IReadOnlyList<string> Tables,
    IReadOnlyList<Suggestion> Suggestions,
    IReadOnlyDictionary<string, IReadOnlyList<string>>? Keys = null,
    double Seconds = 0);
