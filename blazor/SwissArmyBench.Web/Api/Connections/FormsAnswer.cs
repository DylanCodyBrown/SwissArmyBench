namespace SwissArmyBench.Web.Api.Connections;

/// <summary>GET /connections/types: every kind's form.</summary>
public sealed record FormsAnswer(IReadOnlyList<ConnectionForm> Types);
