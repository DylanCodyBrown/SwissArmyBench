namespace SwissArmyBench.Web.Api.Accounting;

/// <summary>A template's place bound to a value or to a table of lines that grows.</summary>
public sealed record TemplateBinding
{
    public string Kind { get; init; } = "value";

    public string Place { get; init; } = string.Empty;

    public BindingValue? Value { get; init; }

    public string? Format { get; init; }

    public IReadOnlyList<string>? Columns { get; init; }

    public int? Rows { get; init; }

    public bool? Grow { get; init; }
}
