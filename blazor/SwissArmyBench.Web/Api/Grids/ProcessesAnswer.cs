namespace SwissArmyBench.Web.Api.Grids;

/// <summary>GET /processes: the Python sessions offering tables.</summary>
public sealed record ProcessesAnswer(IReadOnlyList<SessionTables> Processes);
