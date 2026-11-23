using SwissArmyBench.Web.Api.Git;

namespace SwissArmyBench.Web.Pages.Scm;

/// <summary>A row of a group: a folder (View as Tree) or a file, at its depth.</summary>
public sealed record ChangeRow(string? Folder, ScmResource? File, int Depth);
