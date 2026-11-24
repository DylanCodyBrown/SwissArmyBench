namespace SwissArmyBench.Web.Api.Grids;

/// <summary>GET /sandbox: the open project's sandbox tables (the Tables page reads their bar's words and columns).</summary>
public sealed record SandboxState(IReadOnlyList<SandboxTable> Tables);
