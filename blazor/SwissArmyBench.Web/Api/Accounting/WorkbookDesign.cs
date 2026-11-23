using System.Text.Json;
using System.Text.Json.Serialization;

namespace SwissArmyBench.Web.Api.Accounting;

/// <summary>A workbook's design (workbook.design.json): its title and its sheets. Fields this page does not know
/// are kept, so Undo and Redo send the design back whole.</summary>
public sealed record WorkbookDesign
{
    public int Format { get; init; } = 1;

    public string Kind { get; init; } = "workbook";

    public string Title { get; init; } = string.Empty;

    public IReadOnlyList<WorkbookSheet> Sheets { get; init; } = [];

    [JsonExtensionData]
    public Dictionary<string, JsonElement>? Extra { get; init; }
}
