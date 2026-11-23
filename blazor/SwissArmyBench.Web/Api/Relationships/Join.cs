using System.Text.Json.Serialization;

namespace SwissArmyBench.Web.Api.Relationships;

/// <summary>A relationship between two tables: the columns that join them, its kind (many-to-one...), whether it is
/// used (Run on) or only kept (Run off), what it was found from (the Key Finder's evidence) and its note.</summary>
public sealed record Join(
    string From,
    IReadOnlyList<string> FromColumns,
    string To,
    IReadOnlyList<string> ToColumns,
    string Kind = "many-to-one",
    bool Active = true,
    string? Evidence = null,
    string? Note = null)
{
    /// <summary>The columns it joins on: "customer_id", "id = customer_id".</summary>
    [JsonIgnore]
    public string On => string.Join(", ", FromColumns.Zip(ToColumns).Select(p => p.First == p.Second ? p.First : $"{p.First} = {p.Second}"));

    /// <summary>A join's name: its two ends and their columns (what the server deletes and changes it by).</summary>
    [JsonIgnore]
    public string Key => $"{From}|{string.Join(',', FromColumns)}|{To}|{string.Join(',', ToColumns)}";

    /// <summary>Its two ends only, as the server's delete and update read them.</summary>
    [JsonIgnore]
    public object Ends => new { from = From, from_columns = FromColumns, to = To, to_columns = ToColumns };
}
