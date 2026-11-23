namespace SwissArmyBench.Web.Pages.Scm;

/// <summary>A context menu open at a place, with its label (its aria name).</summary>
public sealed record OpenScmMenu(double X, double Y, string Label, IReadOnlyList<ScmMenuItem?> Items);
