namespace SwissArmyBench.Web.Api.PowerApps;

/// <summary>The environments pac lists.</summary>
public sealed record CodeAppEnvironments
{
    public IReadOnlyList<CodeAppEnvironment> Environments { get; init; } = [];
}
