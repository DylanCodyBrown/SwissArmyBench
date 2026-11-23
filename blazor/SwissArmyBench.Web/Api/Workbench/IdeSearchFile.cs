namespace SwissArmyBench.Web.Api.Workbench;

/// <summary>A file's matches of a search across the scripts.</summary>
public sealed record IdeSearchFile(string Path, IReadOnlyList<IdeSearchMatch> Matches);
