namespace SwissArmyBench.Web.Api.Relationships;

/// <summary>POST /relationships/import (a review): the set read from the file, which of its tables are open, and what
/// applying it would change in the joins in use.</summary>
public sealed record ImportReview(
    ImportedSet Set,
    IReadOnlyList<string> OpenTables,
    IReadOnlyList<string> MissingTables,
    IReadOnlyList<string> Changes);
