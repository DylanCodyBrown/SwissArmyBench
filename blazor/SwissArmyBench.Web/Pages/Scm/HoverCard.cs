namespace SwissArmyBench.Web.Pages.Scm;

/// <summary>A graph row's hover card: the commit and where it shows.</summary>
public sealed record HoverCard(GraphItem Item, double X, double Y);
