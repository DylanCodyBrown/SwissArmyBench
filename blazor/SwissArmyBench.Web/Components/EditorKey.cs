namespace SwissArmyBench.Web.Components;

/// <summary>A key a page acts on, pressed in an editor (run, runHere, runInsert, save, saveAs, runFile, escape),
/// with the editor's text as it was then.</summary>
public sealed record EditorKey(string Name, string Text);
