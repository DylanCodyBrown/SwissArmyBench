namespace SwissArmyBench.Web.Api.Canvas;

/// <summary>Play's, Launch's and a build's relaunch: whether it started, its address, its title and build, or its problem.</summary>
public sealed record RunAnswer
{
    public bool Ok { get; init; }

    public string? Url { get; init; }

    public string? Title { get; init; }

    public int? Build { get; init; }

    public Widgets.WidgetRunProblem? Problem { get; init; }
}
