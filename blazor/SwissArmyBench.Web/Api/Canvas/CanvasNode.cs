using System.Text.Json;

namespace SwissArmyBench.Web.Api.Canvas;

/// <summary>A container or a widget instance in one layout's pixels: its place, its own and its children, its values and wires.</summary>
public sealed record CanvasNode
{
    public string Id { get; init; } = string.Empty;

    public string Kind { get; init; } = string.Empty;

    public string? Show { get; init; }

    public bool Hidden { get; init; }

    public double X { get; init; }

    public double Y { get; init; }

    public double W { get; init; }

    public double H { get; init; }

    public ContainerProps? Props { get; init; }

    public IReadOnlyList<CanvasNode>? Children { get; init; }

    public string? Widget { get; init; }

    public IReadOnlyDictionary<string, JsonElement>? Values { get; init; }

    public IReadOnlyDictionary<string, JsonElement>? Wires { get; init; }
}
