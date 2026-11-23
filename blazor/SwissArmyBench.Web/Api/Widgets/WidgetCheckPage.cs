namespace SwissArmyBench.Web.Api.Widgets;

/// <summary>One page's failures and exceptions in a headless check.</summary>
public sealed record WidgetCheckPage
{
    public IReadOnlyList<string> Failed { get; init; } = [];

    public IReadOnlyList<string> Exceptions { get; init; } = [];
}
