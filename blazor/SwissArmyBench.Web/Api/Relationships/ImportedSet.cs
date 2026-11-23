namespace SwissArmyBench.Web.Api.Relationships;

/// <summary>A relationship set as a file holds it: its name, description, tags, author and joins.</summary>
public sealed record ImportedSet(
    string Name,
    IReadOnlyList<Join> Relationships,
    string Description = "",
    IReadOnlyList<string>? Tags = null,
    string? Author = null);
