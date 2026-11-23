using System.Text.Json;

namespace SwissArmyBench.Web.Api.Accounting;

/// <summary>A table block's colour rule: a column compared with a value, the fill when it holds.</summary>
public sealed record ColourRule
{
    public string Column { get; init; } = string.Empty;

    public string Op { get; init; } = ">";

    public JsonElement? Value { get; init; }

    public JsonElement? To { get; init; }

    public string? Fill { get; init; }
}
