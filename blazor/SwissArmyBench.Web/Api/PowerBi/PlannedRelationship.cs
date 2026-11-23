namespace SwissArmyBench.Web.Api.PowerBi;

/// <summary>One relationship in the plan: its two ends, whether it goes, active, why it is left out.</summary>
public sealed record PlannedRelationship
{
    public string From { get; init; } = string.Empty;

    public IReadOnlyList<string> FromColumns { get; init; } = [];

    public string To { get; init; } = string.Empty;

    public IReadOnlyList<string> ToColumns { get; init; } = [];

    public bool Goes { get; init; }

    public bool Active { get; init; }

    public string? LeftOut { get; init; }

    public string? Note { get; init; }
}
