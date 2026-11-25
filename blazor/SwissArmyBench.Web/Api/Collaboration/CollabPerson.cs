namespace SwissArmyBench.Web.Api.Collaboration;

/// <summary>A person of the Collaboration panel: the name shown and the login a mention names; the agent marked.</summary>
public sealed record CollabPerson(string Name, string Login, bool Agent = false);
