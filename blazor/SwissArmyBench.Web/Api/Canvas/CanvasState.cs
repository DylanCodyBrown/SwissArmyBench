namespace SwissArmyBench.Web.Api.Canvas;

/// <summary>One canvas as the server has it (services/canvas.py state): its model, each page's items per layout, the version a change is made on, its marks and its wiring.</summary>
public sealed record CanvasState
{
    public string Canvas { get; init; } = string.Empty;

    public string Path { get; init; } = string.Empty;

    public string Name { get; init; } = string.Empty;

    public int Version { get; init; }

    public CanvasModel Model { get; init; } = new();

    public string? ReadOnly { get; init; }

    public CanvasBroken? Broken { get; init; }

    public IReadOnlyList<string> Missing { get; init; } = [];

    public IReadOnlyDictionary<string, IReadOnlyDictionary<string, string>> Marks { get; init; } = new Dictionary<string, IReadOnlyDictionary<string, string>>();

    public IReadOnlyList<string> Notes { get; init; } = [];

    public int Undo { get; init; }

    public int Redo { get; init; }

    public string? Made { get; init; }

    public IReadOnlyDictionary<string, IReadOnlyDictionary<string, IReadOnlyList<CanvasNode>>> Views { get; init; } = new Dictionary<string, IReadOnlyDictionary<string, IReadOnlyList<CanvasNode>>>();

    public IReadOnlyDictionary<string, double> Design { get; init; } = new Dictionary<string, double>();

    public CanvasWiring? Wiring { get; init; }
}
