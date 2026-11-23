namespace SwissArmyBench.Web.Api.Relationships;

/// <summary>POST /relationships/find: the finder's suggestions among the tables named.</summary>
public sealed record FindAnswer(IReadOnlyList<string> Tables, IReadOnlyList<Suggestion> Suggestions);
