namespace SwissArmyBench.Web.Api.Canvas;

/// <summary>One build's files, read-only.</summary>
public sealed record BuildFiles
{
    public IReadOnlyDictionary<string, string> Files { get; init; } = new Dictionary<string, string>();
}
