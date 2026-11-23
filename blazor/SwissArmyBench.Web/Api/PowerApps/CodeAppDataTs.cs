using System.Text.Json;

namespace SwissArmyBench.Web.Api.PowerApps;

/// <summary>Use in app's data.ts: the file written, its target, the cells exported, those kept, the typed results.</summary>
public sealed record CodeAppDataTs
{
    public string Written { get; init; } = string.Empty;

    public string Target { get; init; } = string.Empty;

    public IReadOnlyList<JsonElement> Cells { get; init; } = [];

    public IReadOnlyList<JsonElement> Left { get; init; } = [];

    public IReadOnlyList<string> Types { get; init; } = [];
}
