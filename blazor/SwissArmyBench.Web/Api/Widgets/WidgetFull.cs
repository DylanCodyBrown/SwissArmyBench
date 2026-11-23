namespace SwissArmyBench.Web.Api.Widgets;

/// <summary>One widget opened: its entry's fields, its code, its file and the kernel's setup for the editor's intelligence.</summary>
public sealed record WidgetFull
{
    public string Name { get; init; } = string.Empty;

    public string Description { get; init; } = string.Empty;

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

    public string Code { get; init; } = string.Empty;

    public string File { get; init; } = string.Empty;

    public string? KernelPath { get; init; }

    public string KernelSetup { get; init; } = string.Empty;

    public bool Upgradable { get; init; }
}
