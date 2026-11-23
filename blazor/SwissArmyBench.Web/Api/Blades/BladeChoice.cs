namespace SwissArmyBench.Web.Api.Blades;

/// <summary>New blade's choice: a kind or a template, its words and group.</summary>
public sealed record BladeChoice(string Id, string Label, string Group, string Kind, string? Hint = null);
