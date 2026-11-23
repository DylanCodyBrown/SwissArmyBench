namespace SwissArmyBench.Web.State;

/// <summary>One of the page's notes: a short line (Words), or an error from background work (Error).</summary>
public sealed record Note(string? Words, Exception? Error);
