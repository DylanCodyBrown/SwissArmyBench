namespace SwissArmyBench.Web.Api.Collaboration;

/// <summary>GET /collaboration/search: the words searched for and what was found, newest first.</summary>
public sealed record CollabSearch(string Words, IReadOnlyList<CollabFound> Found);
