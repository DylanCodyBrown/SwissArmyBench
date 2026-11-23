namespace SwissArmyBench.Web.Api.Widgets;

/// <summary>A widget's pages run headless: each page's failures and exceptions.</summary>
public sealed record WidgetCheck
{
    public bool Ok { get; init; }

    public IReadOnlyList<WidgetCheckPage> Pages { get; init; } = [];
}
