namespace SwissArmyBench.Web.Api.Canvas;

/// <summary>Two builds (or a build and now) compared file by file.</summary>
public sealed record BuildCompare
{
    public IReadOnlyList<ComparedFile> Files { get; init; } = [];
}
