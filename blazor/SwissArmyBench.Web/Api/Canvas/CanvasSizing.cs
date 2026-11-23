using System.Text.Json;

namespace SwissArmyBench.Web.Api.Canvas;

/// <summary>The canvas's sizing: its columns, row height, gap, snap and the snap's step (1, 2, 4, 8 px or "grid").</summary>
public sealed record CanvasSizing
{
    public int Columns { get; init; }

    public int RowHeight { get; init; }

    public int Gap { get; init; }

    public bool Snap { get; init; }

    public JsonElement Step { get; init; }
}
