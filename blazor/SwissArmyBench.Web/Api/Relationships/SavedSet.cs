namespace SwissArmyBench.Web.Api.Relationships;

/// <summary>A saved relationship set (a .relationships.json file): its name, description, tags, when and by whom it
/// was saved, where it lives (mine, shared, package, environment), its tables (and which are open) and its joins.</summary>
public sealed record SavedSet
{
    public string Name { get; init; } = string.Empty;

    public string Description { get; init; } = string.Empty;

    public IReadOnlyList<string> Tags { get; init; } = [];

    public string SavedAt { get; init; } = string.Empty;

    public string Author { get; init; } = string.Empty;

    public string File { get; init; } = string.Empty;

    public string Where { get; init; } = "mine";

    public IReadOnlyList<string> Tables { get; init; } = [];

    public IReadOnlyList<string> OpenTables { get; init; } = [];

    public int Relationships { get; init; }
}
