namespace SwissArmyBench.Web.Api.Widgets;

/// <summary>A widget's Ins, Outs and Events as its code declares them.</summary>
public sealed record WidgetContract
{
    public IReadOnlyList<WidgetPort> Ins { get; init; } = [];

    public IReadOnlyList<WidgetPort> Outs { get; init; } = [];

    public IReadOnlyList<WidgetPort> Events { get; init; } = [];
}
