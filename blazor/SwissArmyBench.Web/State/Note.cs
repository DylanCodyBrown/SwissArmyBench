namespace SwissArmyBench.Web.State;

/// <summary>One of the page's notes: a short line (Words), or an error from background work (Error); a line may
/// carry one action (the classic toast's Undo, Show).</summary>
public sealed record Note(string? Words, Exception? Error, string? ActionLabel = null, Func<Task>? Action = null);
