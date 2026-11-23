namespace SwissArmyBench.Web.Api.PowerApps;

/// <summary>A folder (its children) or a file.</summary>
public sealed record CodeAppTreeNode
{
    public string Name { get; init; } = string.Empty;

    public string Path { get; init; } = string.Empty;

    public IReadOnlyList<CodeAppTreeNode>? Children { get; init; }
}
