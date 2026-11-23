namespace SwissArmyBench.Web.Api.Canvas;

/// <summary>A canvas file of the project.</summary>
public sealed record CanvasFile
{
    public string Name { get; init; } = string.Empty;

    public string Path { get; init; } = string.Empty;
}
