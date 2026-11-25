namespace SwissArmyBench.Web.Layout.Collaboration;

/// <summary>One line of the composer's `@` or `:` list: its words, a hint beside them, and what picking it types.</summary>
public sealed record CollabPick(string Label, string Hint, string Insert, string Icon);
