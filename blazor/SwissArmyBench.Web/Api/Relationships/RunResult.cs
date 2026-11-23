using System.Text.Json;
using System.Text.Json.Serialization;

namespace SwissArmyBench.Web.Api.Relationships;

/// <summary>One join checked against the open tables: holds, orphans, broken or not open, in words, with a few
/// orphan values and notes.</summary>
public sealed record RunResult
{
    public string From { get; init; } = string.Empty;

    public IReadOnlyList<string> FromColumns { get; init; } = [];

    public string To { get; init; } = string.Empty;

    public IReadOnlyList<string> ToColumns { get; init; } = [];

    public string Status { get; init; } = "holds";

    public string Detail { get; init; } = string.Empty;

    public IReadOnlyList<JsonElement>? OrphanSamples { get; init; }

    public IReadOnlyList<string>? Notes { get; init; }

    [JsonIgnore]
    public string Key => $"{From}|{string.Join(',', FromColumns)}|{To}|{string.Join(',', ToColumns)}";
}
