namespace SwissArmyBench.Web.Api.Canvas;

/// <summary>A canvas's newest build (Launch's builds/&lt;app&gt;/&lt;n&gt;/build.json): its number, when (UTC, ISO), how it
/// went, and how many builds are kept.</summary>
public sealed record CanvasLastBuild(int Number, int Builds = 0, string? Time = null, string? Result = null);
