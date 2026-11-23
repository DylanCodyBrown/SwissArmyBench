namespace SwissArmyBench.Web.State;

/// <summary>One command of the palette (the classic workbenchCommands.ts Command): its id, group, words, keys, why it
/// cannot run now (null: it can), and what it does.</summary>
public sealed record PaletteCommand(
    string Id,
    string Group,
    string Title,
    Func<Task> Run,
    string? Keys = null,
    string? WhyNot = null);
