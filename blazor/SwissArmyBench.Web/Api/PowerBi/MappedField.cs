namespace SwissArmyBench.Web.Api.PowerBi;

/// <summary>One field the report's visuals name, and the field of ours it maps to (matched by name, or picked).</summary>
public sealed record MappedField
{
    public string Table { get; init; } = string.Empty;

    public string Field { get; init; } = string.Empty;

    public string Kind { get; init; } = string.Empty;

    public FieldRef? To { get; init; }

    public bool Matched { get; init; }
}
