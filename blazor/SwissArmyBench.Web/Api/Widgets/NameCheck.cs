namespace SwissArmyBench.Web.Api.Widgets;

/// <summary>A widget's name checked as it is typed: ok, its state and the words.</summary>
public sealed record NameCheck
{
    public bool Ok { get; init; }

    public string State { get; init; } = string.Empty;

    public string Said { get; init; } = string.Empty;
}
