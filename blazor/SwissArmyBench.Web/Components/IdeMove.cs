namespace SwissArmyBench.Web.Components;

/// <summary>An IDE move asked in an editor (definition, references, rename, format): the text as it is, the cursor's
/// line and column (from one), and the word under it.</summary>
public sealed record IdeMove(string Name, string Text, int Line, int Column, string Word);
