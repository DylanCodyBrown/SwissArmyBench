using System.Text.Json;

namespace SwissArmyBench.Web.Api.Grids;

/// <summary>Cross compare's focus: the side filtered, how many of its rows hold the key, and the key.</summary>
public sealed record CompareFocus
{
    public string Side { get; init; } = "left";

    public long Rows { get; init; }

    public IReadOnlyList<JsonElement> Key { get; init; } = [];
}
