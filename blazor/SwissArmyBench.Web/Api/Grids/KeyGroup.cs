namespace SwissArmyBench.Web.Api.Grids;

/// <summary>The compare rows sharing a picked row's key (GET /compares/{id}/key-group): first to last.</summary>
public sealed record KeyGroup(long First, long Last);
