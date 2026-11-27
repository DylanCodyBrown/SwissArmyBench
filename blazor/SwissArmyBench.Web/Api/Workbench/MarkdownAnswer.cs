namespace SwissArmyBench.Web.Api.Workbench;

/// <summary>POST /workbench/markdown: the text (after an edit, with only that block's characters changed), its
/// blocks, and whether the edit changed anything.</summary>
public sealed record MarkdownAnswer(string Text, IReadOnlyList<MarkdownBlock> Blocks, bool Changed);
