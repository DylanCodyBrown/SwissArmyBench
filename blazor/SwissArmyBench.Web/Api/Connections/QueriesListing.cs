namespace SwissArmyBench.Web.Api.Connections;

/// <summary>GET /connections/queries: the queries running and waiting, the last ones finished, the server's start and clock.</summary>
public sealed record QueriesListing(
    IReadOnlyList<RunningQuery> Queries,
    IReadOnlyList<FinishedQuery> Finished,
    IReadOnlyList<SlotStatus> Connections,
    string Started,
    double Now);
