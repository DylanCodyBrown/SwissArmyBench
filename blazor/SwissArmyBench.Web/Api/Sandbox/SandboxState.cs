namespace SwissArmyBench.Web.Api.Sandbox;

/// <summary>GET /sandbox: the open project's sandbox (none: no project), its tables, baseline, checkpoints and change log's line.</summary>
public sealed record SandboxState(
    string? Project,
    IReadOnlyList<SandboxTable> Tables,
    IReadOnlyList<SandboxCheckpoint> Checkpoints,
    string? BaselineAt = null,
    string? LogWords = null,
    IReadOnlyList<string>? MockChoices = null);
