namespace SwissArmyBench.Web.Components;

/// <summary>An editor's selection as codeEditor.js tells it: the selected text ("" when none) and the line it starts
/// on (the cursor's when nothing is selected).</summary>
public sealed record EditorSelection(string Text, int Line);
