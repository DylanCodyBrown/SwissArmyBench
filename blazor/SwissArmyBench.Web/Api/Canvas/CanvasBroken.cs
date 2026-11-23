namespace SwissArmyBench.Web.Api.Canvas;

/// <summary>A canvas file that does not read: its error, its line and where the copy is kept.</summary>
public sealed record CanvasBroken
{
    public string Error { get; init; } = string.Empty;

    public int? Line { get; init; }

    public string Copy { get; init; } = string.Empty;
}
