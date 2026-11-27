namespace SwissArmyBench.Web.Api.Canvas;

/// <summary>A canvas file of the project, with its card's facts on the landing page: how many pages and widgets, its
/// layouts (desktop, phone), its first page's top boxes for a small picture, and its last build (null: never
/// launched). A file that does not read is <see cref="Broken"/>.</summary>
public sealed record CanvasFile
{
    public string Name { get; init; } = string.Empty;

    public string Path { get; init; } = string.Empty;

    public bool Broken { get; init; }

    public int Pages { get; init; }

    public int Widgets { get; init; }

    public IReadOnlyList<string> Layouts { get; init; } = [];

    public IReadOnlyList<CanvasCardBox> Boxes { get; init; } = [];

    public CanvasLastBuild? Launched { get; init; }
}
