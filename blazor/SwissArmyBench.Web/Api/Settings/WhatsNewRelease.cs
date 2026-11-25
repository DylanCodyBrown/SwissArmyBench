namespace SwissArmyBench.Web.Api.Settings;

/// <summary>One release of What's New (WHATSNEW.md): its version, when (UTC), and its two sections' short bullets.</summary>
public sealed record WhatsNewRelease(
    string Version,
    string Time,
    IReadOnlyList<string> Features,
    IReadOnlyList<string> Fixes);
