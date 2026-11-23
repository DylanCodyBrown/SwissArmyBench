namespace SwissArmyBench.Web.Api.Widgets;

/// <summary>Why a widget's run did not start.</summary>
public sealed record WidgetRunProblem
{
    public string Kind { get; init; } = string.Empty;

    public string? Message { get; init; }

    public string? Feature { get; init; }

    public string? Command { get; init; }
}
