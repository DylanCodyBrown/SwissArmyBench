namespace SwissArmyBench.Web.Api.Grids;

/// <summary>A running Python session whose watcher tells the server which tables it holds (names and sizes, never
/// rows).</summary>
public sealed record SessionTables(string Id, string Label, long Pid, IReadOnlyList<SessionTable> Tables);
