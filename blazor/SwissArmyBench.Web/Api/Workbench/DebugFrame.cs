namespace SwissArmyBench.Web.Api.Workbench;

/// <summary>A paused run's frame: its id, function, line, whether it is the script's own, and its file.</summary>
public sealed record DebugFrame(int Id, string Name, int Line, bool Yours, string? Path = null);
