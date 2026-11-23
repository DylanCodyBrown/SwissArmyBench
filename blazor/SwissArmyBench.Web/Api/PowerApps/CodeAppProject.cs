namespace SwissArmyBench.Web.Api.PowerApps;

/// <summary>The code app open (or the last one): its folder, app, environment, data sources and generated files.</summary>
public sealed record CodeAppProject
{
    public bool Open { get; init; }

    public string? Recent { get; init; }

    public string? Folder { get; init; }

    public string? Problem { get; init; }

    public CodeAppInfo? App { get; init; }

    public string? Environment { get; init; }

    public IReadOnlyList<CodeAppSource> Sources { get; init; } = [];

    public IReadOnlyList<CodeAppGenerated> Generated { get; init; } = [];

    public bool VitePlugin { get; init; }
}
