namespace SwissArmyBench.Web.Api.Connections;

/// <summary>GET /connections/{name}/usage: one connection's card, its configuration and where it is used.</summary>
public sealed record ConnectionUsage(string Name, string Type, string Status, string Error, CallsInfo? Calls, IReadOnlyList<LocalNote>? Local, WritesInfo? Writes, ConnectionConfiguration Configuration, IReadOnlyList<ConnectionReference> References);
