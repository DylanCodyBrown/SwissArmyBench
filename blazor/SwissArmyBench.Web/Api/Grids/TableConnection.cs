namespace SwissArmyBench.Web.Api.Grids;

/// <summary>GET /tables/{name}/connection: the connection a table is read from (none: a file, a paste, a push), and
/// whether its last change can be undone.</summary>
public sealed record TableConnection(string Table, string? Connection, string How, bool Undo);
