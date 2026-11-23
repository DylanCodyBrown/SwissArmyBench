namespace SwissArmyBench.Web.Pages.Workbench;

/// <summary>A run of text in one colour (the classic workbenchOutputs.ts span): its classes (ansi-fg-1, ansi-bold...)
/// and, for a 256-colour or true colour, its style.</summary>
public sealed record AnsiPiece(string Text, string Classes, string Style);
