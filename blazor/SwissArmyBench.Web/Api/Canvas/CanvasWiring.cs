using System.Text.Json;

namespace SwissArmyBench.Web.Api.Canvas;

/// <summary>Each instance's contract, the Ins' sources, the Outs' readers, the wires and the broken ones (services/canvas.py).</summary>
public sealed record CanvasWiring
{
    public IReadOnlyDictionary<string, IReadOnlyDictionary<string, JsonElement>> Sources { get; init; } = new Dictionary<string, IReadOnlyDictionary<string, JsonElement>>();

    public IReadOnlyDictionary<string, IReadOnlyList<string>> Readers { get; init; } = new Dictionary<string, IReadOnlyList<string>>();

    public IReadOnlyList<WireLine> Wires { get; init; } = [];

    public IReadOnlyList<BrokenWire> Broken { get; init; } = [];

    public IReadOnlyDictionary<string, OutRef> Outs { get; init; } = new Dictionary<string, OutRef>();

    public IReadOnlyDictionary<string, IReadOnlyList<string>> Columns { get; init; } = new Dictionary<string, IReadOnlyList<string>>();

    public IReadOnlyDictionary<string, InstancePorts> Ports { get; init; } = new Dictionary<string, InstancePorts>();
}
