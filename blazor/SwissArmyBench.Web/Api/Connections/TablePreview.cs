using System.Text.Json;

namespace SwissArmyBench.Web.Api.Connections;

/// <summary>A table's or a file's first rows (a preview, a Test): its columns and rows, a workbook's sheet.</summary>
public sealed record TablePreview(
    IReadOnlyList<string> Columns,
    IReadOnlyList<IReadOnlyList<JsonElement>> Rows,
    string? Sheet = null,
    string? Table = null,
    string? Schema = null,
    long? Total = null);
