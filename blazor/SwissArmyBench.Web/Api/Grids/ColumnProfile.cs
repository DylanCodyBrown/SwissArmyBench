using System.Text.Json;

namespace SwissArmyBench.Web.Api.Grids;

/// <summary>GET /grids/{id}/profile?column=: a column's numbers (blanks, distinct, range, the most common values).</summary>
public sealed record ColumnProfile(string Column, string Type, string Family, long Rows, long Blanks, double BlankPercent, long Distinct, JsonElement Min = default, JsonElement Max = default, double? Mean = null, double? Median = null, IReadOnlyList<ValueCount>? TopValues = null);
