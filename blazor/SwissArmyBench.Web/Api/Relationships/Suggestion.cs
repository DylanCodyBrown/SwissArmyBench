using System.Text.Json.Serialization;

namespace SwissArmyBench.Web.Api.Relationships;

/// <summary>A relationship the finder suggests: its join, how sure it is, its evidence in plain words, whether it is in
/// use already, and whether it is a second path between two tables (kept inactive).</summary>
public sealed record Suggestion(
    string From,
    IReadOnlyList<string> FromColumns,
    string To,
    IReadOnlyList<string> ToColumns,
    string Kind,
    double Confidence,
    IReadOnlyList<string> Reasons,
    bool Known = false,
    string? Evidence = null,
    bool Active = true,
    string? Note = null)
{
    [JsonIgnore]
    public Join AsJoin => new(From, FromColumns, To, ToColumns, Kind, Active, Evidence, Note);
}
