namespace SwissArmyBench.Web.Api.Grids;

/// <summary>Where an open grid's table came from (GET /grids' origin): its kind (file, python, paste, query...) and
/// the connection it was read from, if any.</summary>
public sealed record GridOrigin(string Kind = "unknown", string? Connection = null);
