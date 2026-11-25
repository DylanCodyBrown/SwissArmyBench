namespace SwissArmyBench.Web.Api.Collaboration;

/// <summary>One message of a thread: its Markdown, its author, its reactions and the objects it names.</summary>
public sealed record CollabMessage(
    string Id,
    string Thread,
    string Kind,
    CollabPerson Author,
    string Time,
    string Edited,
    bool Deleted,
    string Body,
    IReadOnlyList<string> Mentions,
    IReadOnlyList<CollabReference> References,
    IReadOnlyList<CollabReaction> Reactions,
    bool Mine);
