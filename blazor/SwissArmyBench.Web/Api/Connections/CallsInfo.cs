namespace SwissArmyBench.Web.Api.Connections;

/// <summary>A connection's calls this session: how many of each kind, the last one and the figures.</summary>
public sealed record CallsInfo(int Total = 0, IReadOnlyDictionary<string, int>? ByKind = null, double? LastUsed = null, string? LastKind = null, bool? LastOk = null, CallFigures? Figures = null);
