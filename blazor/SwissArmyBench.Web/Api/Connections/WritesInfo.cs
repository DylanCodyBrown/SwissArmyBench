namespace SwissArmyBench.Web.Api.Connections;

/// <summary>What a connection kind writes, or why it is read-only, in words.</summary>
public sealed record WritesInfo(bool Writable, string Words = "", string Reason = "");
