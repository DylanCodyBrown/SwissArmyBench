namespace SwissArmyBench.Web.Api.PowerApps;

/// <summary>GET /powerapps/project/file: one file of the open code app, its language, its text, and whether the
/// Power Apps CLI made it (it writes it again when its data source changes).</summary>
public sealed record CodeAppFile
{
    public string Path { get; init; } = string.Empty;

    public string Language { get; init; } = string.Empty;

    public string Text { get; init; } = string.Empty;

    public bool Generated { get; init; }
}
