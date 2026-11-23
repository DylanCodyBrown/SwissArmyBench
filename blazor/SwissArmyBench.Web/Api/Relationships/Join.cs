namespace SwissArmyBench.Web.Api.Relationships;

/// <summary>A relationship between two tables: the columns that join them, its kind (many-to-one...), and whether
/// it is used (Run on) or only kept (Run off).</summary>
public sealed record Join(
    string From,
    IReadOnlyList<string> FromColumns,
    string To,
    IReadOnlyList<string> ToColumns,
    string Kind = "many-to-one",
    bool Active = true);
