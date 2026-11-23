using System.Text.Json;

namespace SwissArmyBench.Web.Api.Widgets;

/// <summary>One property a widget's code makes (a top-level plain value; domain/widget_properties.py): its mask, default, range and choices.</summary>
public sealed record WidgetProp
{
    public string Name { get; init; } = string.Empty;

    public string Type { get; init; } = string.Empty;

    public string Mask { get; init; } = string.Empty;

    public JsonElement Default { get; init; }

    public string Help { get; init; } = string.Empty;

    public double? Minimum { get; init; }

    public double? Maximum { get; init; }

    public double? Step { get; init; }

    public IReadOnlyList<string> Choices { get; init; } = [];

    public string? Of { get; init; }

    public bool Annotated { get; init; }

    public int Line { get; init; }

    public string? Problem { get; init; }
}
