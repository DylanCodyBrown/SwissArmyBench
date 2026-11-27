namespace SwissArmyBench.Web.State;

/// <summary>A page's own answer to a command the agent sent its window (workbench_window): what it gives back
/// (null: it only did something), and where it happened for the Session page's link (a path, a title, a cell's
/// number; never a cell's text).</summary>
public sealed record CommandAnswer(object? Result, string? Path = null, string? Title = null, int? Cell = null);
