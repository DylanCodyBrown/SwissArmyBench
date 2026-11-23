using System.Text.Json;

namespace SwissArmyBench.Web.Api.Blades;

/// <summary>POST /blades/{name}/run: a run's outcome, its printed output, its result (a table: columns, types, rows,
/// total; or a value), its problems, and when it failed the error panel's detail.</summary>
public sealed record BladeRun(
    string Name,
    bool Ok,
    double Seconds,
    JsonElement? Output = null,
    JsonElement? Result = null,
    IReadOnlyList<BladeProblem>? Problems = null,
    string? Error = null,
    JsonElement? ErrorDetail = null);
