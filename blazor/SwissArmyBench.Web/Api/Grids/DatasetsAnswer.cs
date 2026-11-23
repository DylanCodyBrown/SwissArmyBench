namespace SwissArmyBench.Web.Api.Grids;

/// <summary>GET /datasets: every table in memory, and the data budget.</summary>
public sealed record DatasetsAnswer(IReadOnlyList<DatasetEntry> Datasets, DataBudget Budget);
