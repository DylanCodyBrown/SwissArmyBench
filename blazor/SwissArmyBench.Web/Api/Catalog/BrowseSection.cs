namespace SwissArmyBench.Web.Api.Catalog;

/// <summary>One of the tree's sections after the connections (open, sandbox, structures, apis, blades).</summary>
public sealed record BrowseSection(string Kind, string Label, int Count, IReadOnlyList<SearchResult> Items);
