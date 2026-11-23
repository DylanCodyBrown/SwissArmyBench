namespace SwissArmyBench.Web.Api.Workbench;

/// <summary>A debug session's state (GET /workbench/debug, the debug_state notice): idle, running, paused or ended;
/// why, the line, the frames, and the script's output so far.</summary>
public sealed record DebugState(
    string Kernel,
    string State,
    IReadOnlyList<DebugFrame> Frames,
    string? Document = null,
    string Reason = "",
    int? Line = null,
    string? Output = null,
    bool? Ok = null,
    string Error = "");
