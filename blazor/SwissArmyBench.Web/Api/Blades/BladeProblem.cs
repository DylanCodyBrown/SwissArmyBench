namespace SwissArmyBench.Web.Api.Blades;

/// <summary>A lint problem in a blade's code: its place, message, code and source.</summary>
public sealed record BladeProblem(
    int Line,
    string Message,
    int? Col = null,
    string? Code = null,
    string? Source = null,
    string? Severity = null);
