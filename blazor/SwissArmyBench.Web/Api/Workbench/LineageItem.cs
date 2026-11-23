using System.Text.Json;

namespace SwissArmyBench.Web.Api.Workbench;

/// <summary>One value of a lineage node: a table (its rows, columns, first rows and change), a value, a picture, a
/// chart, or one not made yet (missing).</summary>
public sealed record LineageItem(
    string Name,
    string Kind,
    long? Rows,
    long? Columns,
    IReadOnlyList<string>? Names,
    IReadOnlyList<IReadOnlyList<JsonElement>>? Head,
    long? Change,
    string? Text,
    string? Png);
