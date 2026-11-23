namespace SwissArmyBench.Web.Api.Catalog;

/// <summary>The results of one kind, with their count.</summary>
public sealed record SearchGroup(string Kind, string Label, int Count, IReadOnlyList<SearchResult> Results);
