namespace SwissArmyBench.Web.Api.Workbench;

/// <summary>A line of a notebook's Outline (domain/notebook_flow.py): a Markdown heading (its level) or a named cell,
/// its words and its cell's number.</summary>
public sealed record OutlineItem(string Kind, string Text, int? Number, int? Level = null);
