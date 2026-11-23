namespace SwissArmyBench.Web.Api.Widgets;

/// <summary>A property's value checked before it is kept: ok, or what is wrong and the fix.</summary>
public sealed record CheckedValue
{
    public bool Ok { get; init; }

    public string? Said { get; init; }

    public string? Fix { get; init; }
}
