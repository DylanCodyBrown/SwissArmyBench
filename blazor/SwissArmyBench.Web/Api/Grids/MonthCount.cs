namespace SwissArmyBench.Web.Api.Grids;

/// <summary>A date column's rows in one month (the month's first day).</summary>
public sealed record MonthCount(string Month, long Count);
