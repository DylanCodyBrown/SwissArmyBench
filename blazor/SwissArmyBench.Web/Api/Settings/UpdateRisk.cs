namespace SwissArmyBench.Web.Api.Settings;

/// <summary>What an update would lose: the unsaved documents and the running kernels.</summary>
public sealed record UpdateRisk(IReadOnlyList<string> Unsaved, int Kernels = 0);
