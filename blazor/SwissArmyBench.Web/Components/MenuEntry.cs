namespace SwissArmyBench.Web.Components;

/// <summary>One line of a menu: its words, its icon, what it does, and the reason it cannot when it is greyed out.
/// A line of "-" is a separator. Keys: its keyboard shortcut, shown at its right ("Ctrl+S").</summary>
public sealed record MenuEntry(
    string Label,
    string Icon,
    Func<Task> Run,
    string? Disabled = null,
    string? Keys = null)
{
    public static readonly MenuEntry Separator = new("-", string.Empty, () => Task.CompletedTask);

    public bool IsSeparator => Label == "-";
}
