namespace SwissArmyBench.Web.Api.Canvas;

/// <summary>A canvas's builds, newest first.</summary>
public sealed record BuildList
{
    public IReadOnlyList<BuildInfo> Builds { get; init; } = [];
}
