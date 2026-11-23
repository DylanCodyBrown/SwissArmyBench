namespace SwissArmyBench.Web.Api.Panels;

/// <summary>One of a picker's options.</summary>
public sealed record PanelOption
{
    public string Value { get; init; } = string.Empty;

    public string Label { get; init; } = string.Empty;
}
