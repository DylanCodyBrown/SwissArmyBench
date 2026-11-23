namespace SwissArmyBench.Web.Api.Grids;

/// <summary>GET /grids/{id}: a grid's dataset, columns, steps and whether a change can be undone or redone.</summary>
public sealed record GridInfo(string Grid, string Dataset, string Title, long RowCount, IReadOnlyList<GridColumn> Columns, IReadOnlyList<GridStep> Steps, bool CanUndo = false, bool CanRedo = false, StepError? StepError = null, string? Query = null, string SourceKind = "");
