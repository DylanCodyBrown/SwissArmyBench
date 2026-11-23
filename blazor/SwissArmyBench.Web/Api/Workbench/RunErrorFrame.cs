namespace SwissArmyBench.Web.Api.Workbench;

/// <summary>A frame of an error's way: in a cell, a file, a library or the standard library; its line and code, the
/// values of the failing line's parts and the function's variables at that moment.</summary>
public sealed record RunErrorFrame(
    string Where,
    int? Cell,
    string? File,
    string Module,
    string Function,
    int Line,
    int? Col,
    string Code,
    IReadOnlyList<RunErrorValue> Values,
    IReadOnlyList<RunErrorLocal> Locals);
