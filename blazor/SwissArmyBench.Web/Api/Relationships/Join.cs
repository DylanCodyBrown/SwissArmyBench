namespace SwissArmyBench.Web.Api.Relationships;

/// <summary>A relationship between two tables: the columns that join them, its kind (many-to-one...), whether it is
/// used (Run on) or only kept (Run off), and what it was found from (the Key Finder's evidence).</summary>
public sealed record Join(
    string From,
    IReadOnlyList<string> FromColumns,
    string To,
    IReadOnlyList<string> ToColumns,
    string Kind = "many-to-one",
    bool Active = true,
    string? Evidence = null);
