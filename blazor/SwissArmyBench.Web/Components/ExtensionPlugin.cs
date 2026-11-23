namespace SwissArmyBench.Web.Components;

/// <summary>One extension's plug-in: the classic page's id, what kind of plug-in it is (page_action, rail_page,
/// tab_kind, piece), its component, its words, and its address (a page) or the parameter it is opened with.</summary>
public sealed record ExtensionPlugin(string Id, string Kind, Type Component, string Words, string? Where);
