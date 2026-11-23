namespace SwissArmyBench.Web.Api.Workbench;

/// <summary>GET /workbench/environments: what New environment offers: its libraries by group, the presets, the
/// Python versions uv can fetch, and what is always installed.</summary>
public sealed record EnvironmentOffer(
    IReadOnlyList<OfferedLibrary> Libraries,
    IReadOnlyDictionary<string, IReadOnlyList<string>> Presets,
    IReadOnlyList<string> Versions,
    IReadOnlyList<string> Always);
