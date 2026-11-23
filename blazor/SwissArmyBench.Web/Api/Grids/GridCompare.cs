using System.Text.Json;

namespace SwissArmyBench.Web.Api.Grids;

/// <summary>
/// A compare of two grids side by side (routes_compare.py: POST /compares, GET and PATCH /compares/{id}): its keys,
/// its mode (outer, anti, cross, diff), how many rows matched and how many are on one side only, diff mode's
/// columns that differ, and cross compare's focus (the key picked on one side).
/// </summary>
public sealed record GridCompare
{
    public string Compare { get; init; } = string.Empty;

    public string Left { get; init; } = string.Empty;

    public string Right { get; init; } = string.Empty;

    /// <summary>Each key as [left column, right column].</summary>
    public IReadOnlyList<IReadOnlyList<string>> Keys { get; init; } = [];

    public string Mode { get; init; } = "outer";

    /// <summary>Anti join's side: both, left or right.</summary>
    public string AntiSide { get; init; } = "both";

    public CompareDiffOptions Diff { get; init; } = new();

    public long RowCount { get; init; }

    public CompareCounts Counts { get; init; } = new();

    /// <summary>Diff mode only: which matched rows and columns differ.</summary>
    public CompareDiffer? Differ { get; init; }

    /// <summary>Cross compare: the key picked on one side, the other filtered to it.</summary>
    public CompareFocus? Focus { get; init; }

    /// <summary>The keys in words: "customer_id" or "id = customer_id", joined by " + ".</summary>
    public string KeyWords => string.Join(" + ", Keys.Select(k => k[0] == k[1] ? k[0] : $"{k[0]} = {k[1]}"));

    /// <summary>The focused key in words ("42, North"; a null is "(blank)").</summary>
    public static string KeyText(IEnumerable<JsonElement> key) =>
        string.Join(", ", key.Select(v => v.ValueKind == JsonValueKind.Null ? "(blank)" : v.ValueKind == JsonValueKind.String ? v.GetString() : v.GetRawText()));
}
