using System.Text.Json;

namespace SwissArmyBench.Web.Api.Widgets;

/// <summary>One In, Out or Event of a widget's contract (domain/widget_contract.py).</summary>
public sealed record WidgetPort
{
    public string Name { get; init; } = string.Empty;

    public string Direction { get; init; } = string.Empty;

    public string Type { get; init; } = string.Empty;

    public string Words { get; init; } = string.Empty;

    public JsonElement Default { get; init; }

    public string Help { get; init; } = string.Empty;

    public int Line { get; init; }

    public string? Problem { get; init; }

    public IReadOnlyList<PortField> Fields { get; init; } = [];

    public string Schema { get; init; } = string.Empty;
}
