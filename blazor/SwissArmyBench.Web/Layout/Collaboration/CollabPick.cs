namespace SwissArmyBench.Web.Layout.Collaboration;

/// <summary>One line of the composer's `@` or `:` list: its words, a hint beside them, what picking it types, its
/// icon, and the part of the list it is in ("On this page", "People", "In the project").</summary>
public sealed record CollabPick(string Label, string Hint, string Insert, string Icon, string Section = "");
