namespace SwissArmyBench.Web.Components;

/// <summary>
/// How <see cref="MarkdownText"/> draws the Collaboration panel's own links: an object reference (its words, kind,
/// path and id, decoded) and a pasted picture (its words and its file's name). Each answers markup it encoded itself.
/// </summary>
public sealed record MarkdownLinks(
    Func<string, string, string, string, string> Reference,
    Func<string, string, string> Picture);
