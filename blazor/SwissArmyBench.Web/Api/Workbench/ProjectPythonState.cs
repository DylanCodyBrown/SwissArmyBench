namespace SwissArmyBench.Web.Api.Workbench;

/// <summary>GET and POST /environment/python: the open project's own Python (none, making, ready, missing, failed) in
/// words, what the one session means, and a notebook's older environment offered.</summary>
public sealed record ProjectPythonState(
    string Status,
    string Words,
    string Python,
    bool Own,
    string? Problem,
    string? Session,
    IReadOnlyList<PythonOffer>? Offers);
