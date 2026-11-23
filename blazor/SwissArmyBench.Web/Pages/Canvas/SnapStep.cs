using System.Text.Json;

namespace SwissArmyBench.Web.Pages.Canvas;

/// <summary>The snap step: 1, 2, 4 or 8 pixels, or the grid's cells.</summary>
public sealed record SnapStep(int Pixels, bool Grid)
{
    public static readonly SnapStep One = new(1, false);

    /// <summary>The words the server keeps: a number, or "grid".</summary>
    public static SnapStep From(JsonElement step) => step.ValueKind switch
    {
        JsonValueKind.String when step.GetString() == "grid" => new(0, true),
        JsonValueKind.Number => new(step.GetInt32(), false),
        _ => One,
    };

    /// <summary>The value the select box shows ("1" ... "grid").</summary>
    public string Value => Grid ? "grid" : Pixels.ToString(System.Globalization.CultureInfo.InvariantCulture);
}
