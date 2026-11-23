namespace SwissArmyBench.Web.Api.Sandbox;

/// <summary>What has changed in a sandbox table since its baseline.</summary>
public sealed record SandboxChanges(int Inserted = 0, int Updated = 0, int Deleted = 0);
