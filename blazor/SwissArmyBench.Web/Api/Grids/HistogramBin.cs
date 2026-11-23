namespace SwissArmyBench.Web.Api.Grids;

/// <summary>One bar of a number column's histogram: its range and how many rows fall in it.</summary>
public sealed record HistogramBin(double Low, double High, long Count);
