namespace SwissArmyBench.Web.Api.Widgets;

/// <summary>Why a widget's code does not read: the error, its fix and its line.</summary>
public sealed record WidgetProblem
{
    public string Error { get; init; } = string.Empty;

    public string Fix { get; init; } = string.Empty;

    public int? Line { get; init; }
}
