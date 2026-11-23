namespace SwissArmyBench.Web.Api.Widgets;

/// <summary>A widget run alone: whether it started, its address or its problem.</summary>
public sealed record WidgetRun
{
    public bool Ok { get; init; }

    public string? Url { get; init; }

    public WidgetRunProblem? Problem { get; init; }
}
