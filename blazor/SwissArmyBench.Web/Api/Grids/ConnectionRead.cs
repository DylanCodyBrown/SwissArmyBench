namespace SwissArmyBench.Web.Api.Grids;

/// <summary>A connection's table a query read: the connection, the name it was read as, its rows, when, and the
/// filters sent to the source.</summary>
public sealed record ConnectionRead(string Connection, string As, long Rows, string ReadAt, SentWork? Sent = null);
