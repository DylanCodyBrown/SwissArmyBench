namespace SwissArmyBench.Web.Api.Canvas;

/// <summary>An export: its folder, its files, and what to set where it runs.</summary>
public sealed record ExportAnswer
{
    public string Folder { get; init; } = string.Empty;

    public IReadOnlyList<string> Files { get; init; } = [];

    public IReadOnlyList<string> Warnings { get; init; } = [];
}
