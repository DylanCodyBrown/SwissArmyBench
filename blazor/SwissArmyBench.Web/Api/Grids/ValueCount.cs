using System.Text.Json;

namespace SwissArmyBench.Web.Api.Grids;

/// <summary>A value and how many rows hold it (a column's most common values).</summary>
public sealed record ValueCount(JsonElement Value, long Count);
