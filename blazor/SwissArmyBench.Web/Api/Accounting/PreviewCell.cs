namespace SwissArmyBench.Web.Api.Accounting;

/// <summary>A cell as built: its text as formatted, number, bold, italic, size, colours, borders and formula.</summary>
public sealed record PreviewCell
{
    public string? T { get; init; }

    public int? N { get; init; }

    public int? B { get; init; }

    public int? I { get; init; }

    public double? Size { get; init; }

    public string? C { get; init; }

    public string? Fill { get; init; }

    public int? Top { get; init; }

    public int? Bottom { get; init; }

    public string? Formula { get; init; }
}
