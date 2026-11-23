namespace SwissArmyBench.Web.Api.Panels;

/// <summary>A picker: a change posts {choice, value}.</summary>
public sealed record PanelChoice
{
    public string Id { get; init; } = string.Empty;

    public string Label { get; init; } = string.Empty;

    public string Value { get; init; } = string.Empty;

    public IReadOnlyList<PanelOption> Options { get; init; } = [];
}
