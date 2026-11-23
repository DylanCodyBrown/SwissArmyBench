namespace SwissArmyBench.Web.Components;

/// <summary>A line of an editor's right-click menu chosen: its id and the line the cursor (or selection) starts on.</summary>
public sealed record EditorMenuPick(string Id, int Line);
