namespace SwissArmyBench.Web.Api.Workbench;

/// <summary>What a Power Query file's run, problems or composed SQL sends: its file, its text as on screen, and for
/// one query the cursor's line (none: every table of the file).</summary>
public sealed record PowerQueryRequest(string? Path, string Text, int? Line = null, string? Query = null);
