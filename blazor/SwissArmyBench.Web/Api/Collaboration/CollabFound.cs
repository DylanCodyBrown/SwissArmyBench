namespace SwissArmyBench.Web.Api.Collaboration;

/// <summary>One search result: a message (its thread and title) or an activity line, with its snippet.</summary>
public sealed record CollabFound(
    string Type,
    string Time,
    string Snippet,
    string? Thread = null,
    string? Title = null,
    string? Message = null,
    string? Id = null,
    CollabPerson? Author = null,
    IReadOnlyList<string>? Threads = null);
