namespace SwissArmyBench.Web.Api.Workbench;

/// <summary>A file's changed lines in a rename's or a replace's preview.</summary>
public sealed record IdeFilePreview(string Path, IReadOnlyList<IdeLineChange> Lines);
