namespace SwissArmyBench.Web.Api.Grids;

/// <summary>
/// GET /grids/{id}: a grid's dataset, columns, steps and whether a change can be undone or redone. StageColumns are
/// the columns entering each step in order (a step's editor offers those); Settings how its filters compare text.
/// </summary>
public sealed record GridInfo(
    string Grid,
    string Dataset,
    string Title,
    long RowCount,
    IReadOnlyList<GridColumn> Columns,
    IReadOnlyList<GridStep> Steps,
    bool CanUndo = false,
    bool CanRedo = false,
    StepError? StepError = null,
    string? Query = null,
    string SourceKind = "",
    IReadOnlyList<IReadOnlyList<GridColumn>>? StageColumns = null,
    TextMatching? Settings = null);
