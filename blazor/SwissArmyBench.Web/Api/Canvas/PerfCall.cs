namespace SwissArmyBench.Web.Api.Canvas;

/// <summary>One query, outside request or file read: its rerun, kind, block, where, rows and time.</summary>
public sealed record PerfCall
{
    public int? Rerun { get; init; }

    public string Kind { get; init; } = string.Empty;

    public string Block { get; init; } = string.Empty;

    public string? Connection { get; init; }

    public string? Host { get; init; }

    public string? File { get; init; }

    public long? Rows { get; init; }

    public double Ms { get; init; }
}
