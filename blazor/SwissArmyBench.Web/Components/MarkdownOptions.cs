namespace SwissArmyBench.Web.Components;

/// <summary>
/// How <see cref="MarkdownText"/> draws a Markdown file's own parts (the Scripts page's reader): its task boxes
/// live (each numbered within the text: data-task), a picture by its address (its words and the address as written:
/// the answer is markup it encoded itself, null to show the words only) and a link that is not a web address (its
/// drawn words and the address: a file beside it).
/// </summary>
public sealed record MarkdownOptions(
    bool Tasks = false,
    Func<string, string, string?>? Image = null,
    Func<string, string, string?>? Link = null);
