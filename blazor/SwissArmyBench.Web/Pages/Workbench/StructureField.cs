namespace SwissArmyBench.Web.Pages.Workbench;

/// <summary>One field of a structure tab's small dialog (a step's or a key's): its name, label, first value, and its
/// choices when it is a choice.</summary>
public sealed record StructureField(
    string Name,
    string Label,
    string Value = "",
    IReadOnlyList<string>? Options = null);
