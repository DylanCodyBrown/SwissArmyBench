namespace SwissArmyBench.Web.Api.PowerBi;

/// <summary>A table's field.</summary>
public sealed record FieldRef
{
    public string Table { get; init; } = string.Empty;

    public string Field { get; init; } = string.Empty;
}
