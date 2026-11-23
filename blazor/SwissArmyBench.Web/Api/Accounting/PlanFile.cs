using System.Text.Json;

namespace SwissArmyBench.Web.Api.Accounting;

/// <summary>One statement or invoice: its file (or sheet), group, rows, totals, number and date.</summary>
public sealed record PlanFile
{
    public string File { get; init; } = string.Empty;

    public string? Sheet { get; init; }

    public IReadOnlyDictionary<string, JsonElement> Group { get; init; } = new Dictionary<string, JsonElement>();

    public int Rows { get; init; }

    public IReadOnlyDictionary<string, double> Totals { get; init; } = new Dictionary<string, double>();

    public JsonElement? Number { get; init; }

    public string Date { get; init; } = string.Empty;
}
