namespace SwissArmyBench.Web.Api.Collaboration;

/// <summary>One emoji on a message: who reacted with it, and whether one of them is you.</summary>
public sealed record CollabReaction(string Emoji, IReadOnlyList<string> People, bool Mine);
