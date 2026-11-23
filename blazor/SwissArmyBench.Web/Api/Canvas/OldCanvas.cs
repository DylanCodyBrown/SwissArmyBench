namespace SwissArmyBench.Web.Api.Canvas;

/// <summary>An older app file, and what was said about it.</summary>
public sealed record OldCanvas
{
    public string Name { get; init; } = string.Empty;

    public string Said { get; init; } = string.Empty;
}
