namespace SwissArmyBench.Web.Api.Connections;

/// <summary>POST /project/import/sources: what another project's folder offers to import (its connections, by name).</summary>
public sealed record ImportOffered(string From, IReadOnlyList<OfferedConnection> Connections);
