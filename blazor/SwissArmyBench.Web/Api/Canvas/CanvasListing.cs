namespace SwissArmyBench.Web.Api.Canvas;

/// <summary>The open project's canvases (GET /streamlit/canvases), and the older app files with what became of them.</summary>
public sealed record CanvasListing
{
    public string? Folder { get; init; }

    public IReadOnlyList<CanvasFile> Canvases { get; init; } = [];

    public IReadOnlyList<OldCanvas> Old { get; init; } = [];
}
