namespace SwissArmyBench.Web.Api.Relationships;

/// <summary>A relationship between two tables: the columns that join them and its kind (many-to-one...).</summary>
public sealed record Join(string From, IReadOnlyList<string> FromColumns, string To, IReadOnlyList<string> ToColumns, string Kind = "many-to-one");
