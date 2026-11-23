namespace SwissArmyBench.Web.Api.Canvas;

/// <summary>One page of a canvas: its id and name.</summary>
public sealed record CanvasPageModel
{
    public string Id { get; init; } = string.Empty;

    public string Name { get; init; } = string.Empty;
}
