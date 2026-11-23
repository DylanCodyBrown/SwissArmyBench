namespace SwissArmyBench.Web.Api.Widgets;

/// <summary>A typed payload's (or a Table[Row]'s) field.</summary>
public sealed record PortField
{
    public string Name { get; init; } = string.Empty;

    public string Type { get; init; } = string.Empty;
}
