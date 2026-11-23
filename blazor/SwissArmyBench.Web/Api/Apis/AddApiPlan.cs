namespace SwissArmyBench.Web.Api.Apis;

/// <summary>POST /apis/preview (and POST /apis): what Add API would write, written nowhere until Add.</summary>
public sealed record AddApiPlan(
    string Connection,
    string File,
    string Path,
    bool Exists,
    string? Taken,
    IReadOnlyList<PlanVariable> Variables,
    PlanChanges? Changes,
    PlanSpec Spec,
    AddedSaved? Saved = null);
