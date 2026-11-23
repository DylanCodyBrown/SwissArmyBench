namespace SwissArmyBench.Web.Api.Connections;

/// <summary>A connection's running figures this session (times in milliseconds).</summary>
public sealed record CallFigures(int Count = 0, int Errors = 0, double? P50 = null, double? P95 = null);
