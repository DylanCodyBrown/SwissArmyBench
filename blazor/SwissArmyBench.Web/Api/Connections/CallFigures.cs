namespace SwissArmyBench.Web.Api.Connections;

/// <summary>A connection's running figures in the open project (times in milliseconds; names, times and sizes only).</summary>
public sealed record CallFigures(
    int Count = 0,
    int Errors = 0,
    double? P50 = null,
    double? P95 = null,
    double ErrorRate = 0,
    double WaitP95 = 0,
    long Rows = 0,
    int Pages = 0);
