using System.Text.Json;
using System.Text.Json.Serialization;

namespace SwissArmyBench.Web.Api.Accounting;

/// <summary>One sheet of a workbook's design: its name, freeze panes, print setup and blocks.</summary>
public sealed record WorkbookSheet
{
    public string Id { get; init; } = string.Empty;

    public string Name { get; init; } = string.Empty;

    public string? Freeze { get; init; }

    public string? TabColour { get; init; }

    public SheetPrint? Print { get; init; }

    public IReadOnlyList<WorkbookBlock> Blocks { get; init; } = [];

    [JsonExtensionData]
    public Dictionary<string, JsonElement>? Extra { get; init; }
}
