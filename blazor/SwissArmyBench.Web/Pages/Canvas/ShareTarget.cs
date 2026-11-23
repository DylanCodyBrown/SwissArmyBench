namespace SwissArmyBench.Web.Pages.Canvas;

/// <summary>A running app Share… knows (the classic shareApp.ts ShareableApp): its kind, its id and its title.</summary>
public sealed record ShareTarget(string Kind, string Id, string Title);
