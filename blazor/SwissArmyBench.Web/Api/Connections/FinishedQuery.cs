namespace SwissArmyBench.Web.Api.Connections;

/// <summary>A query this session that ended: how long, its rows, OK, cancelled or failed and why.</summary>
public sealed record FinishedQuery(
    string Id,
    string Connection,
    string Who,
    string What,
    IReadOnlyList<string> Targets,
    string Outcome,
    string Reason,
    double EndedAt,
    double Seconds,
    long? Rows = null,
    bool HasSql = false);
