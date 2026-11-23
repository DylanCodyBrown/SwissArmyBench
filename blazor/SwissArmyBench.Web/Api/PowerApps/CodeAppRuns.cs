namespace SwissArmyBench.Web.Api.PowerApps;

/// <summary>This session's runs.</summary>
public sealed record CodeAppRuns
{
    public IReadOnlyList<CodeAppRun> Runs { get; init; } = [];
}
