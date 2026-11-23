namespace SwissArmyBench.Web.Api.Projects;

/// <summary>POST /project/save: where it was saved and its notes (said one by one).</summary>
public sealed record SaveAnswer(string? Saved = null, IReadOnlyList<string>? Notes = null);
