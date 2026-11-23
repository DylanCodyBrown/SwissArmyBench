namespace SwissArmyBench.Web.Api.Connections;

/// <summary>GET /connections/usage: every connection's card.</summary>
public sealed record CardsAnswer(IReadOnlyList<ConnectionCard> Connections);
