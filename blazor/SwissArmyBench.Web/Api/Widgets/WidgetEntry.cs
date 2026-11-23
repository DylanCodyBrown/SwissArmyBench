namespace SwissArmyBench.Web.Api.Widgets;

/// <summary>A widget as the lists show it (services/widgets.py): its words, group and pack, where it lives, its properties and contract, its problem.</summary>
public sealed record WidgetEntry
{
    public string Name { get; init; } = string.Empty;

    public string Description { get; init; } = string.Empty;

    public string Framework { get; init; } = string.Empty;

    public string Group { get; init; } = string.Empty;

    public string Pack { get; init; } = string.Empty;

    public string PackDescription { get; init; } = string.Empty;

    public IReadOnlyList<string> Tags { get; init; } = [];

    public bool Prebuilt { get; init; }

    public string Where { get; init; } = "library";

    public IReadOnlyList<string> Hides { get; init; } = [];

    public IReadOnlyList<WidgetProp> Properties { get; init; } = [];

    public WidgetContract? Contract { get; init; }

    public WidgetProblem? Problem { get; init; }

    public string Hash { get; init; } = string.Empty;
}
