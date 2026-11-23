namespace SwissArmyBench.Web.Api.Canvas;

/// <summary>The canvas file's model: its name, sizing and pages (each page's items are read per layout from the views).</summary>
public sealed record CanvasModel
{
    public string Name { get; init; } = string.Empty;

    public CanvasSizing Sizing { get; init; } = new();

    public IReadOnlyList<CanvasPageModel> Pages { get; init; } = [];
}
