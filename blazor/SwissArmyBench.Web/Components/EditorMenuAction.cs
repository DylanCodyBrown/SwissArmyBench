namespace SwissArmyBench.Web.Components;

/// <summary>A page's line in an editor's own right-click menu (a cell's Lineage): its id and its words.</summary>
public sealed record EditorMenuAction(string Id, string Label);
