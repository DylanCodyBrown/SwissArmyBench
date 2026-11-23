namespace SwissArmyBench.Web.Api.App;

/// <summary>A button an extension that is on adds to a base page (the mode's page_actions): the page it goes on,
/// the plug-in it opens by id, its words, icon and tip.</summary>
public sealed record PageAction(string Page, string Id, string Label, string? Icon = null, string? Title = null);
