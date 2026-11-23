namespace SwissArmyBench.Web.Api.Sandbox;

/// <summary>The client a sandbox table's rows answer as: plain DuckDB, or a mock of a connection's kind.</summary>
public sealed record SandboxMock(string Kind, string? Connection = null, string? Template = null);
