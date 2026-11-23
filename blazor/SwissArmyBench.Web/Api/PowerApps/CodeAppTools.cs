namespace SwissArmyBench.Web.Api.PowerApps;

/// <summary>The tools the page needs on this system.</summary>
public sealed record CodeAppTools
{
    public string System { get; init; } = string.Empty;

    public IReadOnlyList<CodeAppTool> Tools { get; init; } = [];
}
