namespace SwissArmyBench.Web.Api.Relationships;

/// <summary>The answer when a set applied: what it changed in the joins in use, in words.</summary>
public sealed record ChangedWords(IReadOnlyList<string> Changed);
