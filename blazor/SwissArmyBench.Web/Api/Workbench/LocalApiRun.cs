namespace SwissArmyBench.Web.Api.Workbench;

/// <summary>POST /local-api/run: the local sandbox API running (its address and endpoints), or why it failed.</summary>
public sealed record LocalApiRun(LocalApiRunning? Running, LocalApiFailed? Failed);
