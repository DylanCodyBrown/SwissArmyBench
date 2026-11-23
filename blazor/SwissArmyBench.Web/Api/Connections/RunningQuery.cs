namespace SwissArmyBench.Web.Api.Connections;

/// <summary>A query running or waiting in a connection's line: who asked, what and its tables, its place, its rows.</summary>
public sealed record RunningQuery(
    string Id,
    string Connection,
    string Caller,
    string Who,
    string Kind,
    string What,
    IReadOnlyList<string> Targets,
    string State,
    double QueuedAt,
    double? StartedAt = null,
    double Elapsed = 0,
    QuerySource? Source = null,
    bool HasSql = false,
    int? Place = null,
    string? Words = null,
    long? Rows = null);
