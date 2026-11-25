namespace SwissArmyBench.Web.Api.Collaboration;

/// <summary>A channel (#general and the team's own): its name, its key ("#general") and its unread count.</summary>
public sealed record CollabChannel(string Name, string Key, int Unread);
