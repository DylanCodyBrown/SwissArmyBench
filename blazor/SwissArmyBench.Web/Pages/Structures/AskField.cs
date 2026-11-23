namespace SwissArmyBench.Web.Pages.Structures;

/// <summary>One field of a step's dialog: its name, its words, its first value, and its choices (a list) or none (a box).</summary>
public sealed record AskField(string Name, string Label, string Value = "", IReadOnlyList<string>? Options = null);
