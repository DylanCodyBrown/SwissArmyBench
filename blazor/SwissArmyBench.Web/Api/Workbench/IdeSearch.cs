namespace SwissArmyBench.Web.Api.Workbench;

/// <summary>POST /scripts/search's answer: the files with matches, and how many matches.</summary>
public sealed record IdeSearch(IReadOnlyList<IdeSearchFile> Results, int Count);
