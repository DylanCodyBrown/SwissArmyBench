namespace SwissArmyBench.Web.Api.Canvas;

/// <summary>A container's own properties.</summary>
public sealed record ContainerProps
{
    public string Title { get; init; } = string.Empty;

    public bool Border { get; init; }

    public int Padding { get; init; }

    public string Height { get; init; } = "fit";

    public bool Scrollable { get; init; }

    public bool Resizable { get; init; }

    public string Background { get; init; } = string.Empty;

    public int Columns { get; init; } = 12;
}
