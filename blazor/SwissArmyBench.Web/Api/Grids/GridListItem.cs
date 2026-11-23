namespace SwissArmyBench.Web.Api.Grids;

/// <summary>One open grid (GET /grids): its id, its table and how many steps.</summary>
public sealed record GridListItem(string Grid, string Dataset, int Steps = 0);
