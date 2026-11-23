namespace SwissArmyBench.Web.Api.App;

/// <summary>A button an extension that is on adds to a base page (the mode's page_actions): the page, the plug-in's
/// id, its words, icon and title.</summary>
public sealed record PageActionInfo(string Page, string Id, string Label, string Icon = "", string Title = "");
