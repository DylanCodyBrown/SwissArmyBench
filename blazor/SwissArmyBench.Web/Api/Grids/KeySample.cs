using System.Text.Json;

namespace SwissArmyBench.Web.Api.Grids;

/// <summary>POST /grids/{id}/key-finder/sample: a pair's shared values and this column's values the other lacks (a
/// few of each, and how many).</summary>
public sealed record KeySample(
    IReadOnlyList<JsonElement> Matched,
    long MatchedCount,
    IReadOnlyList<JsonElement> Missing,
    long MissingCount);
