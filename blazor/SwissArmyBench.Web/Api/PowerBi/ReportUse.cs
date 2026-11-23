namespace SwissArmyBench.Web.Api.PowerBi;

/// <summary>An existing report's pages used: the file, its kind and pages, our tables' columns, its fields mapped, the measures that come along, what is said.</summary>
public sealed record ReportUse
{
    public string File { get; init; } = string.Empty;

    public string Kind { get; init; } = string.Empty;

    public string Pages { get; init; } = string.Empty;

    public IReadOnlyDictionary<string, IReadOnlyList<string>> Ours { get; init; } = new Dictionary<string, IReadOnlyList<string>>();

    public IReadOnlyList<MappedField> Fields { get; init; } = [];

    public IReadOnlyList<string> Measures { get; init; } = [];

    public IReadOnlyList<string> Said { get; init; } = [];
}
