namespace SwissArmyBench.Web.Api.Canvas;

/// <summary>A saved analyzer session's file in the build.</summary>
public sealed record SavedFile
{
    public string File { get; init; } = string.Empty;
}
