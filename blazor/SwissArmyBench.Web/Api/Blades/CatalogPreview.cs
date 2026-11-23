using System.Text.Json;

namespace SwissArmyBench.Web.Api.Blades;

/// <summary>A table's first rows, read from its connection (nothing kept).</summary>
public sealed record CatalogPreview(IReadOnlyList<string> Columns, IReadOnlyList<IReadOnlyList<JsonElement>> Rows);
