namespace SwissArmyBench.Web.Api.PowerApps;

/// <summary>The code app's files as a tree.</summary>
public sealed record CodeAppFiles
{
    public CodeAppTreeNode Tree { get; init; } = new();
}
