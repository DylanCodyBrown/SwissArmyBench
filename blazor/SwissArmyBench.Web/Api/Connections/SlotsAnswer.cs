namespace SwissArmyBench.Web.Api.Connections;

/// <summary>GET /connections/slots: every connection's slots.</summary>
public sealed record SlotsAnswer(IReadOnlyList<SlotStatus> Connections);
