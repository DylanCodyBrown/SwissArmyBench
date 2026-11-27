namespace SwissArmyBench.Web.Api.Workbench;

/// <summary>One block of a Markdown file (domain/markdown_blocks.py): its place in the list, its kind (front_matter,
/// heading, paragraph, list, table, quote, code, diagram, rule), its first line, its own text, a fenced block's
/// language and how many task boxes it holds.</summary>
public sealed record MarkdownBlock(
    int Index,
    string Kind,
    int Line,
    int Lines,
    string Text,
    string Language = "",
    int Tasks = 0);
