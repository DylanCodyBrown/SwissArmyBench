namespace SwissArmyBench.Web.Api.Grids;

/// <summary>A grid the Key Finder can compare with (GET /grids/{id}/key-finder); Self is this grid.</summary>
public sealed record KeyFinderTarget(string Grid, string Dataset, string Label, bool Self);
