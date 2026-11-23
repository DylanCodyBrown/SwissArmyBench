namespace SwissArmyBench.Web.Api.Sandbox;

/// <summary>A checkpoint of the sandbox: its name and when it was saved.</summary>
public sealed record SandboxCheckpoint(string Name, string At);
