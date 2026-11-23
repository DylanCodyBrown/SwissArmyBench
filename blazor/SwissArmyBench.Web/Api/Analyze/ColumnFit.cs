using System.Text.Json;

namespace SwissArmyBench.Web.Api.Analyze;

/// <summary>An analysis that fits a column, with the columns it runs on (the one click's picks).</summary>
public sealed record ColumnFit(
    string Analysis,
    string Label,
    string Name,
    string Get,
    JsonElement? Columns);
