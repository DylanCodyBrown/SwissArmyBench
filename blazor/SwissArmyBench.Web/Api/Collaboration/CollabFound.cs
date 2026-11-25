namespace SwissArmyBench.Web.Api.Collaboration;

/// <summary>One search result: a message, its thread and title, with its snippet.</summary>
public sealed record CollabFound(
    string Type,
    string Time,
    string Snippet,
    string Thread,
    string? Title = null,
    string? Message = null,
    CollabPerson? Author = null);
