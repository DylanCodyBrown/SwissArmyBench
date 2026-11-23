namespace SwissArmyBench.Web.Api.PowerApps;

/// <summary>The Code App page's state (GET /powerapps): the tools, who is signed in, the environments, the code app open, Run live, this session's runs.</summary>
public sealed record CodeAppState
{
    public CodeAppTools Tools { get; init; } = new();

    public CodeAppAccount? Account { get; init; }

    public IReadOnlyList<CodeAppEnvironment>? Environments { get; init; }

    public CodeAppProject Project { get; init; } = new();

    public CodeAppLive Live { get; init; } = new();

    public IReadOnlyList<CodeAppRun> Runs { get; init; } = [];
}
