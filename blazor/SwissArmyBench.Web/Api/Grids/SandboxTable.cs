namespace SwissArmyBench.Web.Api.Grids;

/// <summary>A sandbox table: its name, its designation ("orders · sandbox"), where it came from in words, whether it
/// is a variant, its columns (and which are keys), and the grid that shows it (sandbox_&lt;name&gt;).</summary>
public sealed record SandboxTable
{
    public string Name { get; init; } = string.Empty;

    public string Title { get; init; } = string.Empty;

    public string SourceWords { get; init; } = string.Empty;

    public string? OriginWords { get; init; }

    public System.Text.Json.JsonElement? Variant { get; init; }

    public string Grid { get; init; } = string.Empty;

    public IReadOnlyList<SandboxColumn> Columns { get; init; } = [];

    public bool IsVariant => Variant is { ValueKind: System.Text.Json.JsonValueKind.Object };
}
