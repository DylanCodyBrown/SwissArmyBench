namespace SwissArmyBench.Web.Api.Grids;

/// <summary>One open grid (GET /grids): its id, its table, how many steps, and where its table came from.</summary>
public sealed record GridListItem(string Grid, string Dataset, int Steps = 0, GridOrigin? Origin = null);
