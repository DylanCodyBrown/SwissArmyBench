namespace SwissArmyBench.Web.Pages.Scm;

/// <summary>One line of a quick pick: its words, its description (greyed) and the value it gives.</summary>
public sealed record PickChoice(string Label, string Value, string? Description = null);
