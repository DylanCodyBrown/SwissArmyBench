namespace SwissArmyBench.Web.Api.Workbench;

/// <summary>A Power Query file's run (POST /scripts/pq/run): every table it built, in the order they ran, and the
/// last one (what the Tables page comes forward on).</summary>
public sealed record PowerQueryRun(IReadOnlyList<PowerQueryTable> Tables, string Grid, string Table, long Rows);
