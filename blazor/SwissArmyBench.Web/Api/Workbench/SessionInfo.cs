namespace SwissArmyBench.Web.Api.Workbench;

/// <summary>A document's Python session: the project's one (Shared, with its words), else null for a loose file's
/// kernel of its own.</summary>
public sealed record SessionInfo(bool Shared, string Words, string? Kernel);
