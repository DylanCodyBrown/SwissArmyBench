using SwissArmyBench.Web.Api.Widgets;

namespace SwissArmyBench.Web.Api.Canvas;

/// <summary>One instance's contract: its page, its widget and its Ins, Outs and Events.</summary>
public sealed record InstancePorts
{
    public string Page { get; init; } = string.Empty;

    public string Widget { get; init; } = string.Empty;

    public IReadOnlyList<WidgetPort> Ins { get; init; } = [];

    public IReadOnlyList<WidgetPort> Outs { get; init; } = [];

    public IReadOnlyList<WidgetPort> Events { get; init; } = [];
}
