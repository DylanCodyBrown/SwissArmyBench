namespace SwissArmyBench.Web.Api.Collaboration;

/// <summary>The team link's word (services/team.py sync_words): behind (Pull), changes (Push), conflicts or an error.</summary>
public sealed record CollabTeam(string State, string Words);
