namespace SwissArmyBench.Web.Pages.Catalog;

/// <summary>One thing a result offers (Open as table, Preview, Copy SQL name…): its words, icon, tooltip, what it does.</summary>
public sealed record ExplorerAction(string Label, string Icon, Func<Task> Run, string? Title = null);
