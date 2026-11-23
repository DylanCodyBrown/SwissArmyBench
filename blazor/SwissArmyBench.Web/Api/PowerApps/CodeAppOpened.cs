namespace SwissArmyBench.Web.Api.PowerApps;

/// <summary>A file or notebook to open: its path.</summary>
public sealed record CodeAppOpened
{
    public string? Open { get; init; }

    public string? Path { get; init; }
}
