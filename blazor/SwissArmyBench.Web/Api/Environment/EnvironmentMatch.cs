namespace SwissArmyBench.Web.Api.Environment;

/// <summary>What a search matched in a row: its own name and words, or its parts (by their place).</summary>
public sealed record EnvironmentMatch(bool Own, IReadOnlyList<int> Kids);
