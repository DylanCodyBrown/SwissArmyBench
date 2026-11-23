namespace SwissArmyBench.Web.Api.Environment;

/// <summary>The project's own Python: its state (none, making, ready, missing, failed) in one line, its version, the one session, a notebook's older environment offered.</summary>
public sealed record EnvironmentPython(
    string Status,
    string Words,
    string Python = "",
    bool Own = false,
    string? Problem = null,
    string? Session = null,
    string Version = "",
    IReadOnlyList<PythonOffer>? Offers = null);
