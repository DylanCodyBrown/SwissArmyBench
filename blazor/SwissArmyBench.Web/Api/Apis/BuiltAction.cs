namespace SwissArmyBench.Web.Api.Apis;

/// <summary>POST /actions/build: where it went (a file and a cell or line), or the code to copy, or the widget put on
/// a canvas.</summary>
public sealed record BuiltAction(
    string As,
    string? Code = null,
    string? Path = null,
    int? Cell = null,
    int? Line = null,
    string? Canvas = null,
    string? Widget = null);
