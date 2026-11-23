namespace SwissArmyBench.Web.Api.Workbench;

/// <summary>One error of a run's chain: its type and message, Python's hint, how it led to the next (cause or
/// context), the frames it went through (YourFrame: the last one in the user's code), what it means, and the
/// fixes the server offers.</summary>
public sealed record RunErrorEntry(
    string Type,
    string Message,
    string Hint,
    string? Relation,
    IReadOnlyList<string> Notes,
    IReadOnlyList<RunErrorFrame> Frames,
    IReadOnlyList<string> Group,
    int? YourFrame,
    string Title,
    string Explanation,
    IReadOnlyList<RunErrorFix> Fixes);
