namespace SwissArmyBench.Web.Api.Widgets;

/// <summary>Upgrade to In/Out applied: the widget as saved.</summary>
public sealed record UpgradeDone
{
    public WidgetFull Saved { get; init; } = new();
}
